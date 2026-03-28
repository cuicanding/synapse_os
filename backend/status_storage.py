"""Status storage for SynapseOS — employee status snapshots + history."""
import json
import os
import time
import gzip
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ─── Data directory ────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SNAPSHOT_PATH = os.path.join(DATA_DIR, "status_current.json")
HISTORY_PATH = os.path.join(DATA_DIR, "status_history.jsonl")

# Config
STALE_THRESHOLD_MINUTES = 5
REPORT_INTERVAL_MINUTES = 15


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def _ts_minutes_ago(minutes: int) -> float:
    return time.time() - minutes * 60


# ─── Status Report Model ──────────────────────────────────────────────────
def make_status_report(data: dict) -> dict:
    """Create a validated status report entry."""
    report = {
        "report_id": f"rpt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{data.get('agent_id', 'unknown')}",
        "agent_id": data.get("agent_id", ""),
        "agent_name": data.get("agent_name", ""),
        "role": data.get("role", ""),
        "domain": data.get("domain", ""),
        "current_task": data.get("current_task", ""),
        "progress": data.get("progress", "idle"),
        "progress_detail": data.get("progress_detail", ""),
        "difficulty": data.get("difficulty") or None,
        "difficulty_level": data.get("difficulty_level", "none"),
        "needs_decision": data.get("needs_decision") or None,
        "needs_help": data.get("needs_help") or None,
        "task_id": data.get("task_id", ""),
        "metadata": data.get("metadata", {}),
        "type": data.get("type", "report"),  # report | difficulty | decision
        "created_at": _now_iso(),
    }
    # Type override based on content
    if report["difficulty"] and report["type"] == "report":
        report["type"] = "difficulty"
    if report["needs_decision"] and report["type"] == "report":
        report["type"] = "decision"
    return report


# ─── Snapshot ─────────────────────────────────────────────────────────────
def load_snapshot() -> dict:
    """Load current status snapshot."""
    _ensure_data_dir()
    if os.path.exists(SNAPSHOT_PATH):
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updated_at": None, "agents": {}}


def update_snapshot(report: dict) -> dict:
    """Update snapshot with new report, return updated snapshot."""
    _ensure_data_dir()
    snapshot = load_snapshot()
    agent_id = report["agent_id"]

    snapshot["agents"][agent_id] = {
        "agent_id": report["agent_id"],
        "agent_name": report["agent_name"],
        "role": report["role"],
        "domain": report["domain"],
        "current_task": report["current_task"],
        "progress": report["progress"],
        "progress_detail": report["progress_detail"],
        "difficulty": report["difficulty"],
        "difficulty_level": report["difficulty_level"],
        "needs_decision": report["needs_decision"],
        "needs_help": report["needs_help"],
        "task_id": report["task_id"],
        "last_report_at": report["created_at"],
        "next_report_at": _next_report_at(report["created_at"]),
        "online_status": "online",
    }
    snapshot["updated_at"] = _now_iso()

    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    return snapshot


def get_panel() -> dict:
    """Get status panel with stale detection."""
    snapshot = load_snapshot()
    now = datetime.now(timezone(timedelta(hours=8)))

    agents = []
    for aid, agent in snapshot.get("agents", {}).items():
        is_stale = False
        if agent.get("last_report_at"):
            try:
                last = datetime.fromisoformat(agent["last_report_at"])
                is_stale = (now - last).total_seconds() > STALE_THRESHOLD_MINUTES * 60
            except (ValueError, TypeError):
                is_stale = True

        agent["is_stale"] = is_stale
        if is_stale:
            agent["online_status"] = "stale"
        agents.append(agent)

    return {
        "updated_at": snapshot.get("updated_at"),
        "agents": agents,
        "stale_threshold_minutes": STALE_THRESHOLD_MINUTES,
    }


def _next_report_at(iso_time: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_time)
        dt = dt + timedelta(minutes=REPORT_INTERVAL_MINUTES)
        return dt.isoformat()
    except (ValueError, TypeError):
        return ""


# ─── History ──────────────────────────────────────────────────────────────
def append_history(report: dict):
    """Append a report to history."""
    _ensure_data_dir()
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")


def get_history(agent_id: Optional[str] = None, type_filter: Optional[str] = None,
                from_time: Optional[str] = None, to_time: Optional[str] = None,
                task_id: Optional[str] = None, page: int = 1, limit: int = 20) -> dict:
    """Get paginated history with filters."""
    _ensure_data_dir()
    if not os.path.exists(HISTORY_PATH):
        return {"total": 0, "page": page, "limit": limit, "records": []}

    records = []
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Apply filters
            if agent_id and r.get("agent_id") != agent_id:
                continue
            if type_filter and r.get("type") != type_filter:
                continue
            if task_id and r.get("task_id") != task_id:
                continue
            if from_time and r.get("created_at", "") < from_time:
                continue
            if to_time and r.get("created_at", "") > to_time:
                continue

            records.append(r)

    # Reverse chronological
    records.reverse()

    total = len(records)
    start = (page - 1) * limit
    end = start + limit
    page_records = records[start:end]

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "records": page_records,
    }


# ─── Seed Data ────────────────────────────────────────────────────────────
def seed_demo_data():
    """Create initial demo status data if empty."""
    snapshot = load_snapshot()
    if snapshot.get("agents"):
        return  # Already has data

    now = _now_iso()
    seed_reports = [
        {
            "agent_id": "susan", "agent_name": "苏珊", "role": "主设计师",
            "domain": "infrastructure", "current_task": "状态面板 UI 设计",
            "progress": "developing", "progress_detail": "设计稿完成 60%，准备对接 API",
            "difficulty": None, "difficulty_level": "none",
            "needs_decision": "汇报间隔选 15 分钟还是 20 分钟？", "needs_help": None,
            "task_id": "task-infra-004",
        },
        {
            "agent_id": "reed", "agent_name": "里德", "role": "开发者",
            "domain": "infrastructure", "current_task": "状态上报 API 开发",
            "progress": "developing", "progress_detail": "后端 API 完成 80%，WebSocket 频道搭建中",
            "difficulty": "WebSocket 在高频消息场景下偶现断连", "difficulty_level": "blocking",
            "needs_decision": None, "needs_help": "需要苏珊协助确认前端重连 UI 策略",
            "task_id": "task-infra-004",
        },
        {
            "agent_id": "guoba", "agent_name": "果爸", "role": "董事长",
            "domain": "", "current_task": "审批 task-infra-004 设计方案",
            "progress": "idle", "progress_detail": "等待苏珊提交设计方案",
            "difficulty": None, "difficulty_level": "none",
            "needs_decision": None, "needs_help": None,
            "task_id": "task-infra-004",
        },
    ]

    for data in seed_reports:
        report = make_status_report(data)
        update_snapshot(report)
        append_history(report)

    print("[status] seeded demo data for 3 agents")
