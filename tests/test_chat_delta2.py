#!/usr/bin/env python3
"""
精确测试 chat.send delta 推送。
- 发给 susan (不太可能有其他并发请求)
- 精确追踪 runId
- 记录所有事件的完整 payload
"""
import asyncio
import json
import sys
import time
import uuid

import websockets

GATEWAY_WS_URL = "ws://127.0.0.1:18559"
GATEWAY_TOKEN = "8f54944406d82d6a8473e738dc23162835f93a26d303aa4f"
TARGET_AGENT = "susan"  # 用 susan 避免干扰


async def main():
    print(f"[TEST] 连接 Gateway...")
    gw_ws = await websockets.connect(
        GATEWAY_WS_URL,
        extra_headers={"Origin": "http://127.0.0.1:18559", "Host": "127.0.0.1:18559"}
    )

    # 接收 challenge
    challenge = json.loads(await gw_ws.recv())
    print(f"[RECV] challenge nonce={challenge.get('payload', {}).get('nonce', '')[:20]}...")

    # connect
    req_id = uuid.uuid4().hex[:8]
    await gw_ws.send(json.dumps({
        "type": "req", "id": req_id, "method": "connect",
        "params": {
            "minProtocol": 3, "maxProtocol": 3,
            "client": {"id": "openclaw-control-ui", "version": "1.0.0", "platform": "linux", "mode": "webchat"},
            "role": "operator",
            "scopes": ["operator.read", "operator.write"],
            "caps": ["tool-events"],
            "auth": {"token": GATEWAY_TOKEN},
        }
    }))

    # 等 connect res
    while True:
        raw = await gw_ws.recv()
        data = json.loads(raw)
        if data.get("type") == "res" and data.get("id") == req_id:
            print(f"[CONNECT] ok={data.get('ok')}")
            break
        # 忽略其他事件 (health 等)
        evt_type = data.get("event", "")
        if evt_type and evt_type not in ("health", "tick"):
            print(f"[EVENT] {evt_type}: {json.dumps(data, ensure_ascii=False)[:200]}")

    # 查找 susan 的 session key
    req_id = uuid.uuid4().hex[:8]
    await gw_ws.send(json.dumps({
        "type": "req", "id": req_id,
        "method": "sessions.list",
        "params": {"activeMinutes": 1440}
    }))

    session_key = None
    while True:
        raw = await gw_ws.recv()
        data = json.loads(raw)
        if data.get("type") == "res" and data.get("id") == req_id:
            sessions = data.get("payload", {}).get("sessions", [])
            print(f"[SESSIONS] 找到 {len(sessions)} 个 session:")
            for s in sessions:
                key = s.get("key", "")
                print(f"  {key} (agent={s.get('agentId')})")
                if f"agent:{TARGET_AGENT}:" in key:
                    session_key = key
            break
        evt_type = data.get("event", "")
        if evt_type and evt_type not in ("health", "tick"):
            print(f"[EVENT] {evt_type}: {json.dumps(data, ensure_ascii=False)[:200]}")

    if not session_key:
        print(f"[ERROR] 没找到 {TARGET_AGENT} 的 session，尝试创建...")
        req_id = uuid.uuid4().hex[:8]
        await gw_ws.send(json.dumps({
            "type": "req", "id": req_id,
            "method": "sessions.create",
            "params": {"agentId": TARGET_AGENT}
        }))
        while True:
            raw = await gw_ws.recv()
            data = json.loads(raw)
            if data.get("type") == "res" and data.get("id") == req_id:
                session_key = data.get("payload", {}).get("key", "")
                print(f"[CREATE] session key: {session_key}")
                break

    print(f"[USE] session key: {session_key}")

    # chat.send
    idempotency_key = uuid.uuid4().hex[:12]
    test_message = "请用中文回复：1+1等于几？只回答数字。"
    send_req_id = uuid.uuid4().hex[:8]

    print()
    print(f"{'='*80}")
    print(f"[SEND] chat.send")
    print(f"  idempotencyKey = {idempotency_key}")
    print(f"  sessionKey = {session_key}")
    print(f"  message = '{test_message}'")
    print(f"{'='*80}")
    print()

    await gw_ws.send(json.dumps({
        "type": "req", "id": send_req_id, "method": "chat.send",
        "params": {
            "sessionKey": session_key,
            "message": test_message,
            "idempotencyKey": idempotency_key
        }
    }))

    # 收集事件
    events = []
    start_time = time.time()
    deadline = start_time + 45
    my_run_final = False

    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(gw_ws.recv(), timeout=2.0)
            data = json.loads(raw)
            ts = time.time() - start_time
            events.append((ts, data))

            t = data.get("type", "")
            evt = data.get("event", "")

            if t == "res" and data.get("id") == send_req_id:
                ok = data.get("ok")
                payload = data.get("payload", {})
                status = payload.get("status", "")
                err = data.get("error", "")
                print(f"[{ts:6.2f}s] RES chat.send | ok={ok} status={status} runId={payload.get('runId', '')} error={str(err)[:100]}")

            elif t == "event" and evt == "chat":
                payload = data.get("payload", {})
                state = payload.get("state", "")
                run_id = payload.get("runId", "")
                msg = payload.get("message", {})
                text = ""
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        text = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
                is_mine = run_id == idempotency_key
                marker = " ★" if is_mine else ""
                print(f"[{ts:6.2f}s] CHAT {state:10s} | runId={run_id[:16]}{marker} | len={len(text):5d} | '{text[:100]}'")
                if is_mine and state in ("final", "error", "aborted"):
                    my_run_final = True

            elif t == "event" and evt == "agent":
                payload = data.get("payload", {})
                stream = payload.get("stream", "")
                run_id = payload.get("runId", "")
                data_field = payload.get("data", {})
                phase = data_field.get("phase", "") if isinstance(data_field, dict) else ""
                text_val = data_field.get("text", "") if isinstance(data_field, dict) else ""
                delta_val = data_field.get("delta", "") if isinstance(data_field, dict) else ""
                is_mine = run_id == idempotency_key
                marker = " ★" if is_mine else ""
                
                if stream == "assistant":
                    print(f"[{ts:6.2f}s] AGENT assistant   | runId={run_id[:16]}{marker} | text='{str(text_val)[:50]}' delta='{str(delta_val)[:50]}'")
                elif stream == "lifecycle":
                    print(f"[{ts:6.2f}s] AGENT lifecycle  | runId={run_id[:16]}{marker} | phase={phase}")
                elif stream == "tool":
                    name = data_field.get("name", "") if isinstance(data_field, dict) else ""
                    tool_phase = data_field.get("phase", "") if isinstance(data_field, dict) else ""
                    print(f"[{ts:6.2f}s] AGENT tool       | runId={run_id[:16]}{marker} | {tool_phase} {name}")
                else:
                    print(f"[{ts:6.2f}s] AGENT {stream:12s} | runId={run_id[:16]}{marker}")

            elif t == "event" and evt in ("session.message", "sessions.changed"):
                payload = data.get("payload", {})
                print(f"[{ts:6.2f}s] {evt:20s} | {json.dumps(payload, ensure_ascii=False)[:150]}")

            elif t == "event" and evt in ("health", "tick"):
                pass  # 静默

            else:
                print(f"[{ts:6.2f}s] {t:5s} {evt:20s} | {json.dumps(data, ensure_ascii=False)[:200]}")

        except asyncio.TimeoutError:
            if my_run_final:
                # 额外等 3 秒
                if time.time() > deadline:
                    break
            continue

    # 汇总
    print()
    print("=" * 80)
    print("汇总分析")
    print("=" * 80)

    my_chat = [(ts, e) for ts, e in events
               if e.get("event") == "chat" and e.get("payload", {}).get("runId") == idempotency_key]
    my_agent = [(ts, e) for ts, e in events
                if e.get("event") == "agent" and e.get("payload", {}).get("runId") == idempotency_key]
    other_chat = [(ts, e) for ts, e in events
                  if e.get("event") == "chat" and e.get("payload", {}).get("runId") != idempotency_key]
    other_agent = [(ts, e) for ts, e in events
                   if e.get("event") == "agent" and e.get("payload", {}).get("runId") != idempotency_key]

    print(f"我的 runId: {idempotency_key}")
    print(f"总事件数: {len(events)}")
    print(f"  我的 chat 事件:     {len(my_chat)}")
    print(f"  我的 agent 事件:    {len(my_agent)}")
    print(f"  其他人 chat 事件:   {len(other_chat)}")
    print(f"  其他人 agent 事件:  {len(other_agent)}")

    my_chat_states = [e[1].get("payload", {}).get("state") for _, e in my_chat]
    print(f"  我的 chat states:   {my_chat_states}")

    my_agent_streams = [e[1].get("payload", {}).get("stream") for _, e in my_agent]
    print(f"  我的 agent streams: {my_agent_streams}")

    my_delta_count = sum(1 for s in my_chat_states if s == "delta")
    my_assistant_count = sum(1 for s in my_agent_streams if s == "assistant")

    print(f"  我的 delta 次数:    {my_delta_count}")
    print(f"  我的 assistant 次数: {my_assistant_count}")

    if my_delta_count == 0:
        print()
        print("⚠️  我的 runId 没有收到 delta!")
        print()
        print("详细分析所有 chat 事件 (包括其他 runId):")
        for ts, e in events:
            if e.get("event") == "chat":
                p = e[1].get("payload", {}) if isinstance(e[1], dict) else e.get("payload", {})
                state = p.get("state", "")
                run_id = p.get("runId", "")
                print(f"  [{ts:6.2f}s] state={state:10s} runId={run_id}")
        
        print()
        print("我的 chat.send res 详情:")
        for ts, e in events:
            if e[1].get("type") == "res" and e[1].get("id") == send_req_id:
                print(f"  完整响应: {json.dumps(e[1], ensure_ascii=False, indent=2)[:500]}")

        # 检查是否有其他 runId 收到了 delta（可能是 Gateway 分配了不同的 runId）
        delta_run_ids = set()
        for ts, e in events:
            if e.get("event") == "chat" and e.get("payload", {}).get("state") == "delta":
                delta_run_ids.add(e.get("payload", {}).get("runId"))
        if delta_run_ids:
            print(f"\n收到 delta 的 runIds: {delta_run_ids}")
            print(f"我的 idempotencyKey: {idempotency_key}")
            if idempotency_key in delta_run_ids:
                print("✅ 我的 runId 确实收到了 delta")
            else:
                print("❌ 我的 runId 没有收到 delta，delta 来自其他 runId")

    else:
        print()
        print("✅ 我的 chat.send 成功收到了 delta 流式推送！")

    try:
        await gw_ws.close()
    except:
        pass


if __name__ == "__main__":
    asyncio.run(main())
