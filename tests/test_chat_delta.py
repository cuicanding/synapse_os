#!/usr/bin/env python3
"""
测试 Gateway chat.send 的 delta 流式推送。
连接 Gateway WS，用 chat.send 发消息，记录所有收到的 event。
"""
import asyncio
import json
import sys
import time
import uuid

import websockets

GATEWAY_WS_URL = "ws://127.0.0.1:18559"
GATEWAY_TOKEN = "8f54944406d82d6a8473e738dc23162835f93a26d303aa4f"

# 发给 reed (我自己)，session key 需要先查找
TARGET_AGENT = "reed"  # susan 或 reed


async def main():
    print(f"[TEST] 连接 Gateway: {GATEWAY_WS_URL}")
    gw_ws = await websockets.connect(
        GATEWAY_WS_URL,
        extra_headers={
            "Origin": "http://127.0.0.1:18559",
            "Host": "127.0.0.1:18559"
        }
    )

    # 1. 接收 connect.challenge
    challenge_raw = await gw_ws.recv()
    challenge = json.loads(challenge_raw)
    print(f"[RECV] challenge: {json.dumps(challenge, ensure_ascii=False)[:200]}")

    nonce = challenge.get("payload", {}).get("nonce", "")

    # 2. 发送 connect 请求 (webchat mode)
    connect_req = {
        "type": "req",
        "id": uuid.uuid4().hex[:8],
        "method": "connect",
        "params": {
            "minProtocol": 3,
            "maxProtocol": 3,
            "client": {
                "id": "openclaw-control-ui",
                "version": "1.0.0",
                "platform": "linux",
                "mode": "webchat"
            },
            "role": "operator",
            "scopes": ["operator.read", "operator.write"],
            "caps": ["tool-events"],  # 声明 tool-events 能力
            "auth": {"token": GATEWAY_TOKEN},
        }
    }
    await gw_ws.send(json.dumps(connect_req))
    print(f"[SEND] connect (mode=webchat, caps=[tool-events])")

    # 3. 接收 connect 响应
    connect_resp = json.loads(await gw_ws.recv())
    print(f"[RECV] connect resp: ok={connect_resp.get('ok')}")
    if not connect_resp.get("ok"):
        print(f"[ERROR] connect failed: {connect_resp.get('error')}")
        await gw_ws.close()
        return

    # 4. 查找 agent 的 session key
    list_req = {
        "type": "req",
        "id": uuid.uuid4().hex[:8],
        "method": "sessions.list",
        "params": {"activeMinutes": 1440}
    }
    await gw_ws.send(json.dumps(list_req))

    session_key = None
    while True:
        raw = await gw_ws.recv()
        data = json.loads(raw)
        if data.get("type") == "res" and data.get("id") == list_req["id"]:
            sessions = data.get("payload", {}).get("sessions", [])
            for s in sessions:
                key = s.get("key", "")
                if f"agent:{TARGET_AGENT}:" in key:
                    session_key = key
                    break
            if not session_key and sessions:
                # 列出所有 session keys 帮助调试
                print(f"[DEBUG] 所有 session keys:")
                for s in sessions:
                    print(f"  - {s.get('key')} (agent={s.get('agentId')})")
            break
        else:
            # 非预期事件，记录
            print(f"[EVENT] (during session list) {json.dumps(data, ensure_ascii=False)[:300]}")

    if not session_key:
        print(f"[ERROR] 没找到 agent '{TARGET_AGENT}' 的 session")
        await gw_ws.close()
        return

    print(f"[FOUND] session key: {session_key}")

    # 5. 用 chat.send 发消息
    idempotency_key = uuid.uuid4().hex[:12]
    test_message = "你好，请简短回复一句话测试。"
    chat_send_req = {
        "type": "req",
        "id": uuid.uuid4().hex[:8],
        "method": "chat.send",
        "params": {
            "sessionKey": session_key,
            "message": test_message,
            "idempotencyKey": idempotency_key
        }
    }
    await gw_ws.send(json.dumps(chat_send_req))
    print(f"[SEND] chat.send (sessionKey={session_key}, message='{test_message}')")
    print(f"[INFO] idempotencyKey (runId) = {idempotency_key}")
    print()
    print("=" * 80)
    print("开始监听所有 event... (等待 30 秒)")
    print("=" * 80)

    # 6. 监听所有 event，持续 30 秒
    events = []
    start_time = time.time()
    deadline = start_time + 30
    chat_send_resp_received = False

    while time.time() < deadline:
        try:
            raw = await asyncio.wait_for(gw_ws.recv(), timeout=2.0)
            data = json.loads(raw)
            ts = time.time() - start_time
            t = data.get("type")
            evt = data.get("event", "")

            # 记录所有事件
            events.append((ts, data))

            # 实时打印
            if t == "event":
                payload = data.get("payload", {})
                state = payload.get("state", "")
                stream = payload.get("stream", "")
                run_id = payload.get("runId", "")

                if evt == "chat":
                    # chat 事件 - 最关键
                    msg = payload.get("message", {})
                    content = msg.get("content", "")
                    text = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))

                    print(f"[{ts:6.2f}s] EVENT chat | state={state:10s} | runId={run_id} | text_len={len(text):5d} | text_preview='{text[:80]}'")

                elif evt == "agent":
                    # agent 事件
                    phase = ""
                    if isinstance(payload.get("data"), dict):
                        phase = payload.get("data", {}).get("phase", "")
                    text_data = ""
                    if isinstance(payload.get("data"), dict):
                        text_data = str(payload.get("data", {}).get("text", ""))[:60]
                        delta_data = str(payload.get("data", {}).get("delta", ""))[:60]
                    print(f"[{ts:6.2f}s] EVENT agent | stream={stream:12s} | phase={phase:10s} | runId={run_id} | text='{text_data}' | delta='{delta_data}'")

                elif evt == "session.message":
                    role = payload.get("message", {}).get("role", "")
                    content = payload.get("message", {}).get("content", "")
                    text = ""
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                    print(f"[{ts:6.2f}s] EVENT session.message | role={role:10s} | text_len={len(text):5d} | text_preview='{text[:80]}'")

                else:
                    print(f"[{ts:6.2f}s] EVENT {evt:25s} | {json.dumps(payload, ensure_ascii=False)[:120]}")

            elif t == "res":
                req_id = data.get("id", "")
                ok = data.get("ok")
                status = ""
                if isinstance(data.get("payload"), dict):
                    status = data.get("payload", {}).get("status", "")
                run_id_from_resp = ""
                if isinstance(data.get("payload"), dict):
                    run_id_from_resp = data.get("payload", {}).get("runId", "")

                if status:
                    print(f"[{ts:6.2f}s] RES {req_id} | ok={ok} | status={status} | runId={run_id_from_resp}")
                    if status == "started":
                        chat_send_resp_received = True
                else:
                    print(f"[{ts:6.2f}s] RES {req_id} | ok={ok} | {json.dumps(data.get('payload', data.get('error', '')), ensure_ascii=False)[:120]}")

                # 检查是否收到 final/error/aborted，可以提前结束
                if evt == "" and isinstance(data.get("payload"), dict):
                    p = data["payload"]
                    if p.get("status") in ("ok", "error") and chat_send_resp_received:
                        # chat.send 的最终 res
                        pass

            else:
                print(f"[{ts:6.2f}s] {t:5s} | {json.dumps(data, ensure_ascii=False)[:200]}")

        except asyncio.TimeoutError:
            # 检查是否已经收到 final 状态
            has_final = any(
                e[1].get("event") == "chat" and e[1].get("payload", {}).get("state") == "final"
                for e in events
            )
            has_error = any(
                e[1].get("event") == "chat" and e[1].get("payload", {}).get("state") == "error"
                for e in events
            )
            if has_final or has_error:
                # 多等 2 秒看有没有后续事件
                if time.time() > deadline - 2:
                    break
            continue

    # 7. 汇总分析
    print()
    print("=" * 80)
    print("汇总分析")
    print("=" * 80)

    chat_events = [e for e in events if e[1].get("event") == "chat"]
    agent_events = [e for e in events if e[1].get("event") == "agent"]
    session_msg_events = [e for e in events if e[1].get("event") == "session.message"]

    print(f"总事件数: {len(events)}")
    print(f"  chat 事件:     {len(chat_events)}")
    print(f"  agent 事件:    {len(agent_events)}")
    print(f"  session.message: {len(session_msg_events)}")

    chat_states = [e[1].get("payload", {}).get("state") for e in chat_events]
    print(f"  chat states:   {chat_states}")

    agent_streams = [e[1].get("payload", {}).get("stream") for e in agent_events]
    print(f"  agent streams: {agent_streams}")

    delta_count = sum(1 for s in chat_states if s == "delta")
    print(f"  delta 事件数:  {delta_count}")

    if delta_count == 0:
        print()
        print("⚠️  没有收到 delta 事件！")
        print()
        print("所有 agent 事件详情:")
        for ts, e in agent_events:
            p = e[1].get("payload", {})
            stream = p.get("stream", "")
            data = p.get("data", {})
            print(f"  [{ts:6.2f}s] stream={stream} phase={data.get('phase', '')} "
                  f"has_text={isinstance(data.get('text'), str)} "
                  f"has_delta={isinstance(data.get('delta'), str)} "
                  f"keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}")
    else:
        print()
        print("✅ 收到了 delta 事件！流式推送正常工作。")

    # 清理
    try:
        await gw_ws.close()
    except:
        pass


if __name__ == "__main__":
    asyncio.run(main())
