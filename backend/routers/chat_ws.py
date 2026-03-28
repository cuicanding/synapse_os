"""SynapseOS Workbench Chat - WebSocket bridge to OpenClaw Gateway.

Lightweight: on connect → load last 30 history messages from transcript file.
On send → forward to Gateway, stream response back.
"""
import asyncio
import fcntl
import json
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import websockets

router = APIRouter()

GATEWAY_WS_URL = "ws://127.0.0.1:18559"
GATEWAY_TOKEN = "8f54944406d82d6a8473e738dc23162835f93a26d303aa4f"

# 聊天消息持久化目录
CHAT_HISTORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "chat_history")
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)
_history_lock = threading.Lock()

# Per-agent session key mapping
AGENT_SESSION_KEYS = {
    "main": "agent:main:synapse",
    "susan": "agent:susan:synapse",
    "reed": "agent:reed:synapse",
    "zhouhuajian": "agent:zhouhuajian:synapse",
    "renxianqi": "agent:renxianqi:synapse",
    "aniu": "agent:aniu:synapse",
    "zhouxingchi": "agent:zhouxingchi:synapse",
}

# Agent 显示名称映射
AGENT_DISPLAY_NAMES = {
    "main": {"name": "果爸", "emoji": "👑", "role": "董事长"},
    "susan": {"name": "苏珊", "emoji": "🎨", "role": "主设计师"},
    "reed": {"name": "里德", "emoji": "🔧", "role": "架构师"},
    "zhouhuajian": {"name": "周华健", "emoji": "📊", "role": "策略分析师"},
    "renxianqi": {"name": "任贤齐", "emoji": "💻", "role": "策略开发师"},
    "aniu": {"name": "阿牛", "emoji": "💻", "role": "策略开发师"},
    "zhouxingchi": {"name": "周星驰", "emoji": "🗄️", "role": "策略数据工程师"},
}

# 频道类型定义
# domain-{name} - 域群聊频道
# dm-{agentId} - 与某个 Agent 的单聊频道
CHANNEL_MEMBERS = {
    "domain-infra": ["susan", "reed"],
    "domain-quant": ["zhouhuajian", "renxianqi", "aniu", "zhouxingchi"],
}

# 频道显示信息
CHANNEL_DISPLAY = {
    "domain-infra": {"name": "基础设施域", "icon": "🔧"},
    "domain-quant": {"name": "金蟾量化", "icon": "🦎"},
}

# 频道消息完全走磁盘持久化（JSONL），不使用内存缓存

# 预定义的频道列表（包含 DM 频道）
def get_all_channels():
    """获取所有可用频道列表（域群聊 + DM 频道）"""
    channels = []
    # 添加域群聊频道
    for channel_id, _ in CHANNEL_MEMBERS.items():
        display = CHANNEL_DISPLAY.get(channel_id, {"name": channel_id, "icon": "💬"})
        channels.append({
            "id": channel_id,
            "type": "domain",
            "name": display["name"],
            "icon": display["icon"],
            "members": get_channel_members(channel_id),
        })
    # 添加 DM 频道
    for agent_id in AGENT_SESSION_KEYS:
        profile = AGENT_DISPLAY_NAMES.get(agent_id, {})
        channels.append({
            "id": f"dm-{agent_id}",
            "type": "dm",
            "name": profile.get("name", agent_id),
            "icon": profile.get("emoji", "👤"),
            "targetAgent": agent_id,
        })
    return channels


def is_domain_channel(channel_id: str) -> bool:
    """判断是否为域群聊频道"""
    return channel_id.startswith("domain-")


def is_dm_channel(channel_id: str) -> bool:
    """判断是否为 DM 频道"""
    return channel_id.startswith("dm-")


def get_channel_members(channel_id: str) -> list[dict]:
    """获取频道的成员列表，返回完整成员对象"""
    members = []
    agent_ids = []
    if is_domain_channel(channel_id):
        agent_ids = CHANNEL_MEMBERS.get(channel_id, [])
    elif is_dm_channel(channel_id):
        agent_id = channel_id[3:]  # 去掉 "dm-" 前缀
        if agent_id in AGENT_SESSION_KEYS:
            agent_ids = [agent_id]

    for aid in agent_ids:
        profile = AGENT_DISPLAY_NAMES.get(aid, {})
        members.append({
            "id": aid,
            "name": profile.get("name", aid),
            "status": "online",  # 简单处理，后续可接入真实状态
            "role": profile.get("role", ""),
            "emoji": profile.get("emoji", "👤"),
        })
    return members


def get_dm_target_agent(channel_id: str) -> str | None:
    """获取 DM 频道的目标 Agent ID"""
    if is_dm_channel(channel_id):
        agent_id = channel_id[3:]  # 去掉 "dm-" 前缀
        return agent_id if agent_id in AGENT_SESSION_KEYS else None
    return None


def add_message_to_channel(channel_id: str, sender_id: str, sender_name: str, content: str, role: str = "user"):
    """添加消息到频道历史（纯磁盘持久化，无内存缓存）。"""
    message = {
        "id": uuid.uuid4().hex[:12],
        "senderId": sender_id,
        "senderName": sender_name,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "role": role,
    }
    _persist_message(channel_id, message)
    return message


def _persist_message(channel_id: str, message: dict):
    """将单条消息追加到频道的 JSONL 持久化文件。"""
    try:
        safe_id = channel_id.replace("/", "_").replace("\\", "_")
        filepath = os.path.join(CHAT_HISTORY_DIR, f"{safe_id}.jsonl")
        with _history_lock:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[ws:chat] Failed to persist message: {e}")
        sys.stdout.flush()


def get_channel_history(channel_id: str, limit: int = 50) -> list[dict]:
    """获取频道历史消息（纯磁盘读取）。"""
    return _load_history_from_disk(channel_id, limit=limit)


def extract_text(content):
    """Extract plain text from content (list or string)."""
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
        return "\n".join(texts)
    elif isinstance(content, str):
        return content
    return str(content)


def _load_history_from_disk(channel_id: str, limit: int = 50) -> list[dict]:
    """从频道的 JSONL 持久化文件加载历史消息。"""
    try:
        safe_id = channel_id.replace("/", "_").replace("\\", "_")
        filepath = os.path.join(CHAT_HISTORY_DIR, f"{safe_id}.jsonl")
        if not os.path.isfile(filepath):
            return []

        messages = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    messages.append(msg)
                except json.JSONDecodeError:
                    continue

        return messages[-limit:]
    except Exception as e:
        print(f"[ws:chat] Failed to load history from disk: {e}")
        sys.stdout.flush()
        return []


async def gateway_connect():
    gw_ws = await websockets.connect(
        GATEWAY_WS_URL,
        extra_headers={"Origin": "http://127.0.0.1:18559", "Host": "127.0.0.1:18559"}
    )
    await gw_ws.recv()
    await gw_ws.send(json.dumps({
        "type": "req", "id": uuid.uuid4().hex[:8], "method": "connect",
        "params": {
            "minProtocol": 3, "maxProtocol": 3,
            "client": {"id": "openclaw-control-ui", "version": "1.0.0", "platform": "linux", "mode": "webchat"},
            "role": "operator", "scopes": ["operator.read", "operator.write"],
            "auth": {"token": GATEWAY_TOKEN},
        }
    }))
    resp = json.loads(await gw_ws.recv())
    if not resp.get("ok"):
        raise ConnectionError(f"Gateway auth failed: {resp.get('error')}")
    return gw_ws


async def gw_request(gw_ws, msg_queue, method, params, timeout=10):
    """Send request to Gateway and wait for matching response."""
    rid = uuid.uuid4().hex[:8]
    await gw_ws.send(json.dumps({"type": "req", "id": rid, "method": method, "params": params}))
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return None
        try:
            data = await asyncio.wait_for(msg_queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            return None
        if data is None:
            return None
        if data.get("type") == "res" and data.get("id") == rid:
            return data
        await msg_queue.put(data)


async def ensure_session(gw_ws, msg_queue, agent_id):
    """Ensure session exists, return its key."""
    key = AGENT_SESSION_KEYS.get(agent_id, f"agent:main:{agent_id}")
    resp = await gw_request(gw_ws, msg_queue, "sessions.list", {"activeMinutes": 43200})
    if resp and resp.get("ok"):
        for s in resp.get("payload", {}).get("sessions", []):
            if s.get("key") == key:
                return key
    resp = await gw_request(gw_ws, msg_queue, "sessions.create", {
        "agentId": agent_id, "sessionKey": key
    })
    if resp and resp.get("ok"):
        return key
    return key


@router.get("/api/chat/sync-session")
async def sync_from_session(agent_id: str, limit: int = 50):
    """从 OpenClaw agent session 文件读取最新消息，返回标准化历史。"""
    if not agent_id or agent_id not in AGENT_SESSION_KEYS:
        return {"error": f"Unknown agent: {agent_id}"}, 400

    session_dir = os.path.expanduser(f"~/.openclaw-can/agents/{agent_id}/sessions")
    if not os.path.isdir(session_dir):
        return {"messages": []}

    # 找最新的 session 文件
    session_files = sorted(
        [f for f in os.listdir(session_dir) if f.endswith(".jsonl")],
        key=lambda f: os.path.getmtime(os.path.join(session_dir, f)),
        reverse=True,
    )
    if not session_files:
        return {"messages": []}

    # 读取最新 session 文件，从后往前取 limit 条用户/助手消息
    messages = []
    latest_path = os.path.join(session_dir, session_files[0])
    with open(latest_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "message":
            continue
        msg = entry.get("message", {})
        role = msg.get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        text = _extract_session_text(content)
        if not text or text == "NO_REPLY":
            continue
        messages.append({
            "id": entry.get("id", ""),
            "senderId": agent_id if role == "assistant" else "user",
            "senderName": AGENT_DISPLAY_NAMES.get(agent_id, {}).get("name", agent_id) if role == "assistant" else "果爸",
            "content": text,
            "timestamp": entry.get("timestamp", ""),
            "role": role,
        })
        if len(messages) >= limit:
            break

    messages.reverse()  # 恢复时间顺序
    return {"messages": messages, "session_file": session_files[0]}


def _extract_session_text(content) -> str:
    """Extract displayable text from session message content."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, str):
                texts.append(part.strip())
            elif isinstance(part, dict):
                ptype = part.get("type", "")
                if ptype == "text":
                    t = part.get("text", "").strip()
                    if t and t != "NO_REPLY":
                        texts.append(t)
                elif ptype == "toolCall":
                    name = part.get("name", part.get("toolName", ""))
                    texts.append(f"🔧 {name}")
                elif ptype == "toolResult":
                    # skip tool results in history view
                    continue
        return "\n".join(texts).strip()
    return ""


@router.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    # Auth check
    import os as _os
    _synapse_token = _os.environ.get("SYNAPSE_TOKEN", "")
    if _synapse_token:
        if ws.cookies.get("synapse_token", "") != _synapse_token:
            await ws.send_text(json.dumps({"type": "error", "content": "Unauthorized"}))
            await ws.close(code=4401)
            return
    print(f"[ws:chat] Client connected")
    sys.stdout.flush()

    gw_ws = None
    msg_queue: asyncio.Queue = asyncio.Queue()
    reader_task = None

    # 频道相关状态
    current_channel = "domain-infra"  # 默认加入第一个域群聊频道
    current_agent = "main"  # 保留向后兼容
    session_keys: dict[str, str] = {}

    # Per-agent streaming buffers & runId→agent/channel mapping to prevent cross-talk
    streaming_buffers: dict[str, str] = {}
    # runId -> {"agent": agent_id, "channel": channel_id} 用于正确路由回复
    run_to_info: dict[str, dict] = {}
    done_sent: set[str] = set()  # agents that already received "done" this round
    agent_streamed: set[str] = set()  # agents that received agent.assistant deltas (to skip duplicate chat.delta)

    def resolve_agent(payload: dict) -> str:
        """Determine which agent a Gateway event belongs to via runId."""
        run_id = payload.get("runId", "")
        info = run_to_info.get(run_id, {})
        return info.get("agent", "")

    def resolve_channel(payload: dict) -> str:
        """Determine which channel a Gateway event belongs to via runId."""
        run_id = payload.get("runId", "")
        info = run_to_info.get(run_id, {})
        return info.get("channel", "")

    async def gateway_reader():
        try:
            async for raw in gw_ws:
                data = json.loads(raw)
                t = data.get("type")
                if t in ("res", "event"):
                    await msg_queue.put(data)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"[ws:chat] Reader error: {e}")
        finally:
            await msg_queue.put(None)

    try:
        gw_ws = await gateway_connect()
        reader_task = asyncio.create_task(gateway_reader())

        # 初始化所有 Agent 的 session keys
        for agent_id in AGENT_SESSION_KEYS:
            key = AGENT_SESSION_KEYS[agent_id]
            session_keys[agent_id] = key

        # 发送频道列表给客户端
        channels = get_all_channels()
        await ws.send_json({"type": "channel_list", "channels": channels})
        print(f"[ws:chat] Sent {len(channels)} channels")

        # 发送默认频道的历史消息
        default_history = get_channel_history(current_channel, limit=50)
        members = get_channel_members(current_channel)
        await ws.send_json({
            "type": "channel_joined",
            "channelId": current_channel,
            "history": default_history,
            "members": members,
        })
        print(f"[ws:chat] Joined default channel {current_channel}, sent {len(default_history)} messages")
        sys.stdout.flush()

        while True:
            # Drain gateway events (non-blocking)
            while True:
                try:
                    data = msg_queue.get_nowait()
                    if data is None:
                        await ws.close()
                        return
                    t = data.get("type")
                    if t == "event":
                        event = data.get("event", "")
                        payload = data.get("payload", {})
                        stream = payload.get("stream", "")
                        agent_id = resolve_agent(payload)

                        # Only process events from agents we manage (via runToInfo mapping)
                        if not agent_id or agent_id not in AGENT_SESSION_KEYS:
                            continue

                        ch_id = resolve_channel(payload)
                        if not ch_id:
                            continue

                        if event == "agent":
                            if stream == "assistant":
                                delta = payload.get("data", {}).get("delta", "")
                                if delta and agent_id not in done_sent:
                                    agent_streamed.add(agent_id)
                                    streaming_buffers[agent_id] = streaming_buffers.get(agent_id, "") + delta
                                    await ws.send_json({"type": "delta", "content": delta, "agent": agent_id, "channelId": ch_id})
                            elif stream in ("thinking", "reasoner"):
                                delta = payload.get("data", {}).get("delta", "") or payload.get("data", {}).get("text", "")
                                if delta and agent_id not in done_sent:
                                    await ws.send_json({"type": "thinking", "content": delta, "agent": agent_id, "channelId": ch_id})
                            elif stream == "lifecycle":
                                phase = payload.get("data", {}).get("phase", "")
                                if phase == "end" and agent_id not in done_sent:
                                    done_sent.add(agent_id)
                                    buf = streaming_buffers.get(agent_id, "")
                                    if buf:
                                        # Already have streaming content, send final done
                                        agent_streamed.discard(agent_id)
                                        streaming_buffers.pop(agent_id, "")
                                        # 持久化 Agent 回复到磁盘
                                        profile = AGENT_DISPLAY_NAMES.get(agent_id, {})
                                        add_message_to_channel(ch_id, agent_id, profile.get("name", agent_id), buf, "assistant")
                                        await ws.send_json({"type": "done", "agent": agent_id, "channelId": ch_id})
                                    # else: defer done to chat.final which has the complete message

                        elif event == "chat":
                            chat_state = payload.get("state", "")
                            if chat_state == "delta":
                                # Skip if we already got content via agent.assistant stream (avoid duplicates)
                                if agent_id not in done_sent and agent_id not in agent_streamed:
                                    msg_data = payload.get("message", {})
                                    content = msg_data.get("content", "")
                                    text = extract_text(content)
                                    if text:
                                        streaming_buffers[agent_id] = streaming_buffers.get(agent_id, "") + text
                                        await ws.send_json({"type": "delta", "content": text, "agent": agent_id, "channelId": ch_id})
                            elif chat_state == "final":
                                msg_data = payload.get("message", {})
                                content = msg_data.get("content", "")
                                text = extract_text(content)

                                if agent_id not in done_sent:
                                    # Normal flow: no lifecycle/end seen yet
                                    done_sent.add(agent_id)
                                    buf = streaming_buffers.pop(agent_id, "")
                                    # 确定最终文本
                                    final_text = text
                                    if not buf and text:
                                        final_text = text
                                    elif buf and text and text != buf:
                                        final_text = text
                                    elif buf:
                                        final_text = buf
                                    # 持久化 Agent 回复到磁盘
                                    if final_text:
                                        profile = AGENT_DISPLAY_NAMES.get(agent_id, {})
                                        add_message_to_channel(ch_id, agent_id, profile.get("name", agent_id), final_text, "assistant")
                                    if not buf and text:
                                        await ws.send_json({"type": "delta", "content": text, "agent": agent_id, "channelId": ch_id})
                                    elif buf and text and text != buf:
                                        await ws.send_json({"type": "delta", "content": text, "agent": agent_id, "channelId": ch_id})
                                    await ws.send_json({"type": "done", "agent": agent_id, "channelId": ch_id})
                                else:
                                    # lifecycle/end arrived first but didn't send done (no streaming content)
                                    # Now deliver the complete message
                                    if text:
                                        await ws.send_json({"type": "delta", "content": text, "agent": agent_id, "channelId": ch_id})
                                    await ws.send_json({"type": "done", "agent": agent_id, "channelId": ch_id})
                                agent_streamed.discard(agent_id)
                                streaming_buffers.pop(agent_id, "")
                                run_id = payload.get("runId", "")
                                run_to_info.pop(run_id, None)
                            elif chat_state == "error":
                                err = payload.get("error", {})
                                err_text = err.get("message", "Unknown error") if isinstance(err, dict) else str(err)
                                await ws.send_json({"type": "error", "content": err_text, "agent": agent_id, "channelId": ch_id})
                                streaming_buffers.pop(agent_id, "")
                                run_id = payload.get("runId", "")
                                run_to_info.pop(run_id, None)
                except asyncio.QueueEmpty:
                    break

            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=1.0)
                msg = json.loads(raw)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break

            msg_type = msg.get("type")

            if msg_type == "switch_agent":
                # 已废弃：新版客户端使用频道而非 agent 切换，忽略此消息
                pass

            elif msg_type == "join_channel":
                # 切换频道
                new_channel = msg.get("channelId", "")
                if new_channel:
                    current_channel = new_channel
                    history = get_channel_history(new_channel, limit=50)
                    members = get_channel_members(new_channel)
                    await ws.send_json({
                        "type": "channel_joined",
                        "channelId": new_channel,
                        "history": history,
                        "members": members,
                    })
                    print(f"[ws:chat] Joined channel {new_channel}, sent {len(history)} messages, {len(members)} members")
                    sys.stdout.flush()

            elif msg_type == "reset_session":
                # 重置 DM 频道的 agent session
                channel_id = msg.get("channelId", current_channel)
                if is_dm_channel(channel_id):
                    agent_id = channel_id[3:]
                    if agent_id in AGENT_SESSION_KEYS:
                        key = AGENT_SESSION_KEYS[agent_id]
                        # 1. 销毁旧 session
                        destroy_resp = await gw_request(gw_ws, msg_queue, "sessions.destroy", {
                            "sessionKey": key,
                        }, timeout=10)
                        print(f"[ws:chat] Session destroy for {agent_id}: {destroy_resp}")
                        # 2. 重新创建 session
                        create_resp = await gw_request(gw_ws, msg_queue, "sessions.create", {
                            "agentId": agent_id,
                            "sessionKey": key,
                        }, timeout=10)
                        print(f"[ws:chat] Session create for {agent_id}: {create_resp}")
                        # 3. 清空频道的历史消息（删除磁盘文件）
                        safe_id = channel_id.replace("/", "_").replace("\\", "_")
                        filepath = os.path.join(CHAT_HISTORY_DIR, f"{safe_id}.jsonl")
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        # 4. 通知前端重置成功
                        await ws.send_json({
                            "type": "session_reset",
                            "channelId": channel_id,
                            "agentId": agent_id,
                            "success": True,
                        })
                        print(f"[ws:chat] Session reset done for {agent_id}")
                        sys.stdout.flush()
                    else:
                        await ws.send_json({
                            "type": "session_reset",
                            "channelId": channel_id,
                            "agentId": agent_id,
                            "success": False,
                            "error": f"Unknown agent: {agent_id}",
                        })

            elif msg_type == "send_message":
                content = msg.get("message", "")
                channel_id = msg.get("channelId", current_channel)

                # 更新当前频道
                if channel_id and channel_id != current_channel:
                    current_channel = channel_id

                # 存储消息到频道历史
                add_message_to_channel(channel_id, "user", "果爸", content, "user")

                # 广播给频道的所有成员 Agent
                if is_domain_channel(channel_id):
                    members = CHANNEL_MEMBERS.get(channel_id, [])
                    for agent_id in members:
                        if agent_id not in session_keys:
                            key = await ensure_session(gw_ws, msg_queue, agent_id)
                            session_keys[agent_id] = key
                        key = session_keys[agent_id]

                        done_sent.discard(agent_id)
                        agent_streamed.discard(agent_id)
                        idempotency_key = uuid.uuid4().hex
                        resp = await gw_request(gw_ws, msg_queue, "chat.send", {
                            "sessionKey": key,
                            "message": content,
                            "idempotencyKey": idempotency_key,
                        })
                        if resp and resp.get("ok"):
                            run_id = resp.get("payload", {}).get("runId", "")
                            if run_id:
                                run_to_info[run_id] = {"agent": agent_id, "channel": channel_id}
                            run_to_info[idempotency_key] = {"agent": agent_id, "channel": channel_id}
                            # 立即通知前端：Agent 已收到消息，正在思考
                            profile = AGENT_DISPLAY_NAMES.get(agent_id, {})
                            await ws.send_json({
                                "type": "agent_thinking",
                                "agent": agent_id,
                                "agentName": profile.get("name", agent_id),
                                "channelId": channel_id,
                            })
                        print(f"[ws:chat] → {channel_id}/{agent_id}: {content[:60]}")
                        sys.stdout.flush()

                elif is_dm_channel(channel_id):
                    # DM: 只发给目标 Agent
                    agent_id = channel_id[3:]  # 去掉 dm- 前缀
                    if agent_id not in session_keys:
                        key = await ensure_session(gw_ws, msg_queue, agent_id)
                        session_keys[agent_id] = key
                    key = session_keys[agent_id]

                    done_sent.discard(agent_id)
                    agent_streamed.discard(agent_id)
                    idempotency_key = uuid.uuid4().hex
                    resp = await gw_request(gw_ws, msg_queue, "chat.send", {
                        "sessionKey": key,
                        "message": content,
                        "idempotencyKey": idempotency_key,
                    })
                    if resp and resp.get("ok"):
                        run_id = resp.get("payload", {}).get("runId", "")
                        if run_id:
                            run_to_info[run_id] = {"agent": agent_id, "channel": channel_id}
                        run_to_info[idempotency_key] = {"agent": agent_id, "channel": channel_id}
                        # 立即通知前端：Agent 已收到消息，正在思考
                        profile = AGENT_DISPLAY_NAMES.get(agent_id, {})
                        await ws.send_json({
                            "type": "agent_thinking",
                            "agent": agent_id,
                            "agentName": profile.get("name", agent_id),
                            "channelId": channel_id,
                        })

                    print(f"[ws:chat] → {channel_id}/{agent_id}: {content[:60]}")
                    sys.stdout.flush()

    except Exception as e:
        print(f"[ws:chat] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if reader_task:
            reader_task.cancel()
        if gw_ws:
            try:
                await gw_ws.close()
            except:
                pass
        print(f"[ws:chat] Cleaned up")
        sys.stdout.flush()
