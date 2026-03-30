"""
自动聚合 API - 从 session 文件和 STATUS.md 自动提取员工活动数据。

不再依赖 agent 主动上报，而是从已有数据源自动推导：
- 协作动态: runs.json (subagent spawns)
- 员工状态: STATUS.md (空闲/忙碌 + 当前任务)
- 今日动态: session files (实际对话记录)
"""
import json
import os
import re
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

# ─── Paths ────────────────────────────────────────────────────────────────
AGENTS_DIR = os.path.expanduser("~/.openclaw-can/agents")
RUNS_PATH = os.path.expanduser("~/.openclaw-can/subagents/runs.json")

AGENT_IDS = ["main", "susan", "reed", "zhouhuajian", "renxianqi", "aniu", "zhouxingchi"]

AGENT_PROFILES = {
    "main":        {"name": "果爸",   "emoji": "👑", "role": "董事长"},
    "susan":       {"name": "苏珊",   "emoji": "🎨", "role": "主设计师"},
    "reed":        {"name": "里德",   "emoji": "🔧", "role": "架构师"},
    "zhouhuajian": {"name": "周华健", "emoji": "📊", "role": "策略分析师"},
    "renxianqi":   {"name": "任贤齐", "emoji": "💻", "role": "策略开发师"},
    "aniu":        {"name": "阿牛",   "emoji": "💻", "role": "策略开发师"},
    "zhouxingchi": {"name": "周星驰", "emoji": "🗄️", "role": "数据工程师"},
}

# ─── Cache ────────────────────────────────────────────────────────────────
_cache_lock = threading.Lock()
_cache = {
    "collaborations": {"data": None, "ts": 0, "ttl": 30},
    "agent_statuses": {"data": None, "ts": 0, "ttl": 30},
    "today_activities": {"data": None, "ts": 0, "ttl": 60},
}


def _cached(key: str, ttl_override: int = None):
    """Decorator-like cache check. Returns (data, stale)."""
    entry = _cache.get(key)
    if entry is None:
        return None, True
    ttl = ttl_override or entry["ttl"]
    if entry["data"] is not None and (time.time() - entry["ts"]) < ttl:
        return entry["data"], False
    return entry["data"], True


def _set_cache(key: str, data):
    with _cache_lock:
        _cache[key]["data"] = data
        _cache[key]["ts"] = time.time()


# ─── Helpers ───────────────────────────────────────────────────────────────

def _ms_to_iso(ms_val) -> str:
    """Convert millisecond timestamp or ISO string to ISO string."""
    if not ms_val:
        return ""
    if isinstance(ms_val, (int, float)):
        return datetime.fromtimestamp(ms_val / 1000, tz=timezone.utc).isoformat()
    return str(ms_val)


def _relative_time(dt_str: str) -> str:
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        secs = diff.total_seconds()
        if secs < 60:
            return "刚刚"
        elif secs < 3600:
            return f"{int(secs / 60)}分钟前"
        elif secs < 86400:
            return f"{int(secs / 3600)}小时前"
        elif secs < 172800:
            return f"{int(secs / 86400)}天前"
        else:
            return f"{int(secs / 86400)}天前"
    except Exception:
        return ""


def _extract_agent(session_key: str) -> str:
    parts = session_key.split(":")
    return parts[1] if len(parts) >= 2 else "unknown"


def _extract_session_text(content) -> str:
    """Extract displayable text from session message content."""
    if isinstance(content, str):
        text = content.strip()
        if text and text != "NO_REPLY" and not text.startswith("OpenClaw runtime context"):
            return text
        return ""
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, str):
                t = part.strip()
                if t and t != "NO_REPLY":
                    texts.append(t)
            elif isinstance(part, dict):
                ptype = part.get("type", "")
                if ptype == "text":
                    t = part.get("text", "").strip()
                    if t and t != "NO_REPLY" and not t.startswith("OpenClaw runtime context"):
                        texts.append(t)
        return "\n".join(texts).strip()
    return ""


def _get_latest_session_file(agent_id: str) -> Optional[str]:
    """Get the most recently modified session file for an agent."""
    session_dir = os.path.join(AGENTS_DIR, agent_id, "sessions")
    if not os.path.isdir(session_dir):
        return None
    files = [f for f in os.listdir(session_dir) if f.endswith(".jsonl")]
    if not files:
        return None
    files.sort(key=lambda f: os.path.getmtime(os.path.join(session_dir, f)), reverse=True)
    return os.path.join(session_dir, files[0])


def _get_today_start() -> str:
    """Return ISO string for today's start in local timezone."""
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat()


# ─── 1. 协作动态 (from runs.json) ────────────────────────────────────────

def get_collaborations() -> dict:
    """Get collaboration records from runs.json with proper timestamp handling."""
    cached, stale = _cached("collaborations")
    if not stale:
        return cached

    collaborations = []

    if os.path.exists(RUNS_PATH):
        try:
            with open(RUNS_PATH, "r") as f:
                runs_data = json.load(f)
            runs = runs_data.get("runs", [])
            if isinstance(runs, dict):
                runs = list(runs.values())
        except Exception:
            runs = []

        for run in runs:
            controller_key = run.get("controllerSessionKey", "")
            child_key = run.get("childSessionKey", "")
            task = run.get("task", "") or ""

            from_agent = _extract_agent(controller_key)
            to_agent = _extract_agent(child_key)
            from_profile = AGENT_PROFILES.get(from_agent, {})
            to_profile = AGENT_PROFILES.get(to_agent, {})

            created_at = _ms_to_iso(run.get("createdAt", ""))
            ended_at = _ms_to_iso(run.get("endedAt", ""))
            outcome = run.get("outcome", {}) or {}

            if ended_at and outcome.get("status") == "ok":
                status = "completed"
            elif ended_at:
                status = "failed"
            else:
                status = "running"

            # Task summary
            summary = task.strip()
            lines = summary.split("\n")
            content_lines = [l for l in lines if not l.startswith("#")]
            summary = "\n".join(content_lines).strip()[:80]

            collaborations.append({
                "id": run.get("runId", ""),
                "initiator": from_profile.get("name", from_agent),
                "initiator_agent": from_agent,
                "executor": to_profile.get("name", to_agent),
                "executor_agent": to_agent,
                "task_summary": summary,
                "label": run.get("label", ""),
                "status": status,
                "created_at": created_at,
                "ended_at": ended_at,
                "relative_time": _relative_time(created_at),
            })

        collaborations.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        collaborations = collaborations[:50]

    result = {"collaborations": collaborations, "total": len(collaborations)}
    _set_cache("collaborations", result)
    return result


# ─── 2. 员工状态 (from STATUS.md) ───────────────────────────────────────

def get_agent_statuses() -> dict:
    """Read each agent's STATUS.md to get current status."""
    cached, stale = _cached("agent_statuses")
    if not stale:
        return cached

    agents = []
    for agent_id in AGENT_IDS:
        profile = AGENT_PROFILES.get(agent_id, {})
        status_path = os.path.join(AGENTS_DIR, agent_id, "STATUS.md")

        status = "offline"
        current_task = "—"
        last_update = ""
        working_state = "🟢 空闲"

        if os.path.isfile(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Extract working state
                m = re.search(r"工作状态\*\*[:：]\s*(.+)", content)
                if m:
                    working_state = m.group(1).strip()

                if "🟡 忙碌" in working_state:
                    status = "busy"
                elif "🟢 空闲" in working_state:
                    status = "idle"
                else:
                    status = "unknown"

                # Extract current task
                m = re.search(r"当前任务\*\*[:：]\s*(.+)", content)
                if m:
                    current_task = m.group(1).strip()
                    if current_task in ("无", "—", "-", ""):
                        current_task = "等待新任务指派"

                # Extract last update
                m = re.search(r"最后更新\*\*[:：]\s*(.+)", content)
                if m:
                    last_update = m.group(1).strip()
            except Exception:
                pass

        # Check if agent has recent session activity (last 30 min)
        session_file = _get_latest_session_file(agent_id)
        last_active = ""
        if session_file:
            mtime = os.path.getmtime(session_file)
            last_active_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            last_active = last_active_dt.isoformat()
            age_minutes = (datetime.now(timezone.utc) - last_active_dt).total_seconds() / 60
            if age_minutes < 30:
                if status == "offline":
                    status = "idle"
            elif age_minutes < 60:
                pass  # recent but not super active

        agents.append({
            "agent_id": agent_id,
            "name": profile.get("name", agent_id),
            "emoji": profile.get("emoji", "👤"),
            "role": profile.get("role", ""),
            "status": status,
            "working_state": working_state,
            "current_task": current_task,
            "last_update": last_update,
            "last_active": last_active,
            "relative_active": _relative_time(last_active) if last_active else "",
        })

    result = {"agents": agents}
    _set_cache("agent_statuses", result)
    return result


# ─── 3. 今日动态 (from session files) ─────────────────────────────────────

def get_today_activities(agent_id: Optional[str] = None) -> dict:
    """Extract today's activity from session files."""
    cached, stale = _cached("today_activities")
    if not stale and agent_id is None:
        return cached

    today_start = _get_today_start()
    activities = []

    target_agents = [agent_id] if agent_id else AGENT_IDS

    for aid in target_agents:
        session_dir = os.path.join(AGENTS_DIR, aid, "sessions")
        if not os.path.isdir(session_dir):
            continue

        profile = AGENT_PROFILES.get(aid, {})

        # Get all session files modified today
        for fname in os.listdir(session_dir):
            if not fname.endswith(".jsonl"):
                continue
            filepath = os.path.join(session_dir, fname)

            # Only process files modified today
            mtime = os.path.getmtime(filepath)
            file_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            today_date = datetime.now().strftime("%Y-%m-%d")
            if file_date != today_date:
                continue

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
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
                        if not text:
                            continue

                        timestamp = entry.get("timestamp", "")
                        if not timestamp:
                            continue

                        # Filter: only today's messages
                        # timestamp is like "2026-03-30T10:30:39.795Z"
                        try:
                            msg_dt = timestamp[:10]  # "2026-03-30"
                            if msg_dt != today_date:
                                continue
                        except Exception:
                            continue

                        # Determine activity type
                        if role == "assistant":
                            activity_type = "reply"
                        else:
                            activity_type = "received"

                        summary = text[:120].replace("\n", " ")

                        activities.append({
                            "agent_id": aid,
                            "agent_name": profile.get("name", aid),
                            "agent_emoji": profile.get("emoji", "👤"),
                            "role": role,
                            "type": activity_type,
                            "content": summary,
                            "timestamp": timestamp,
                            "relative_time": _relative_time(timestamp),
                        })
            except Exception:
                continue

    # Sort by timestamp desc
    activities.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    activities = activities[:100]

    result = {"activities": activities, "total": len(activities)}
    _set_cache("today_activities", result)
    return result
