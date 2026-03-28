"""SynapseOS 2.0 Backend - FastAPI + WebSocket Server."""
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from parser import load_all
from watcher import DataWatcher
from status_storage import (
    make_status_report, update_snapshot, get_panel, append_history,
    get_history, load_snapshot, seed_demo_data,
)
from status_reporter import run_report as run_status_report

# Register routers


# ─── Globals ───────────────────────────────────────────────────────────────
CYBER_TEAM_DIR = os.environ.get(
    "CYBER_TEAM_DIR",
    os.path.expanduser("~/.openclaw/workspace-can/cyber-team"),
)
WS_DEBOUNCE_MS = 300

connected_clients: list[WebSocket] = []
status_clients: list[WebSocket] = []  # Separate channel for status updates
watcher: DataWatcher = None
_debounce_task: asyncio.Task | None = None


# ─── Helpers ────────────────────────────────────────────────────────────────
def get_data():
    return load_all()


async def broadcast(payload: dict):
    if not connected_clients:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            connected_clients.remove(ws)
        except ValueError:
            pass


async def on_data_changed():
    global _debounce_task
    if _debounce_task and not _debounce_task.done():
        _debounce_task.cancel()
    _debounce_task = asyncio.create_task(_debounce_and_broadcast())


async def broadcast_status(payload: dict):
    """Broadcast to status WebSocket channel."""
    if not status_clients:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    dead = []
    for ws in status_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            status_clients.remove(ws)
        except ValueError:
            pass


async def _debounce_and_broadcast():
    await asyncio.sleep(WS_DEBOUNCE_MS / 1000)
    data = get_data()
    await broadcast({
        "type": "data_updated",
        "payload": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ─── Status Reporter Cron ─────────────────────────────────────────────────
import threading

_status_reporter_task: threading.Thread | None = None
_stop_reporter = threading.Event()

# Thread-safe signal: set when a new status snapshot is written
_status_changed = threading.Event()

def _status_reporter_loop():
    """Background thread: scan task files every 60s and update status snapshot."""
    import time as _time
    while not _stop_reporter.wait(60):
        try:
            result = run_status_report()
            agents = result.get("agents", {})
            if agents:
                _status_changed.set()   # signal async loop to broadcast
                print(f"[status_reporter] updated {len(agents)} agents")
        except Exception as e:
            print(f"[status_reporter] error: {e}")


# ─── Lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global watcher, _status_reporter_task

    # Start task file watcher (for data_updated WS channel)
    watcher = DataWatcher(CYBER_TEAM_DIR)
    watcher.on_change(on_data_changed)
    await watcher.start()

    # Run first report immediately so panel is populated on startup
    try:
        run_status_report()
        print("[status_reporter] initial report done")
    except Exception as e:
        print(f"[status_reporter] initial report failed: {e}")

    # Start background reporter thread (scans task files every 60s)
    _stop_reporter.clear()
    _status_reporter_task = threading.Thread(target=_status_reporter_loop, daemon=True)
    _status_reporter_task.start()
    print("[status_reporter] started")

    # Async task: listen for status changes and broadcast to /ws/status clients
    _broadcast_task: asyncio.Task | None = None

    async def _status_broadcast_loop():
        while True:
            await asyncio.sleep(0.5)
            if _stop_reporter.is_set():
                break
            if _status_changed.is_set():
                _status_changed.clear()
                try:
                    panel = get_panel()
                    await broadcast_status({
                        "type": "status_updated",
                        "payload": {"panel": panel},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as e:
                    print(f"[status_broadcast] error: {e}")

    print("[app] startup complete")
    yield  # ← app is running

    # Start broadcast task after yield (event loop is fully running)
    _broadcast_task = asyncio.create_task(_status_broadcast_loop())

    # Shutdown
    _stop_reporter.set()
    if _broadcast_task:
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass
    if _status_reporter_task:
        _status_reporter_task.join(timeout=5)
    if watcher:
        await watcher.stop()
    print("[app] shutdown complete")
    print("[app] shutdown complete")


# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="SynapseOS 2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from routers.chat_ws import router as chat_ws_router

# Register routers
app.include_router(chat_ws_router)

# ─── REST API ────────────────────────────────────────────────────────────────
@app.get("/api/missions")
async def api_missions():
    """Return all missions."""
    data = get_data()
    return data.get("missions", [])


@app.get("/api/missions/{mission_id}")
async def api_mission_detail(mission_id: str):
    """Return a single mission with its related tasks."""
    data = get_data()
    missions = data.get("missions", [])
    m = next((m for m in missions if m["id"] == mission_id), None)
    if not m:
        return {"error": f"Mission {mission_id} not found"}, 404
    related_tasks = [t for t in data.get("tasks", []) if t.get("mission_id") == mission_id]
    return {**m, "tasks": related_tasks}


@app.get("/api/mission")
async def api_mission():
    data = get_data()
    return data.get("mission") or {"id": "mission-001", "title": "SynapseOS 2.0", "status": "active"}


@app.get("/api/tasks")
async def api_tasks():
    data = get_data()
    return data.get("tasks", [])

@app.get("/api/collaboration")
async def api_collaboration():
    """Return recent spawn collaboration records from runs.json."""
    runs_path = os.path.expanduser("~/.openclaw-can/subagents/runs.json")
    if not os.path.exists(runs_path):
        return {"collaborations": [], "total": 0}
    try:
        with open(runs_path, "r") as f:
            runs_data = json.load(f)
        runs = runs_data.get("runs", [])
        if isinstance(runs, dict):
            runs = list(runs.values())
    except Exception:
        return {"collaborations": [], "total": 0}

    # Agent name mapping
    name_map = {
        "main": "主控", "reed": "里德", "susan": "苏珊",
        "zhouhuajian": "周华健", "zhouxingchi": "周星驰",
        "renxianqi": "任贤齐", "aniu": "阿牛",
    }

    def extract_agent(session_key: str) -> str:
        parts = session_key.split(":")
        return parts[1] if len(parts) >= 2 else "unknown"

    collaborations = []
    for run in runs:
        run_id = run.get("runId", "")
        controller_key = run.get("controllerSessionKey", "")
        child_key = run.get("childSessionKey", "")
        task = run.get("task", "") or ""
        label = run.get("label", "") or ""
        created_at = run.get("createdAt", "")
        ended_at = run.get("endedAt", "")
        outcome = run.get("outcome", {}) or {}

        from_agent = extract_agent(controller_key)
        to_agent = extract_agent(child_key)
        from_name = name_map.get(from_agent, from_agent)
        to_name = name_map.get(to_agent, to_agent)

        # Status
        if ended_at and outcome.get("status") == "ok":
            status = "completed"
        elif ended_at:
            status = "failed"
        else:
            status = "running"

        # Task summary (first 80 chars, strip markdown headers)
        summary = task.strip()
        lines = summary.split("\n")
        content_lines = [l for l in lines if not l.startswith("#")]
        summary = "\n".join(content_lines).strip()[:80]

        # Relative time
        if created_at:
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                diff = now - dt
                if diff.total_seconds() < 60:
                    relative = "刚刚"
                elif diff.total_seconds() < 3600:
                    relative = f"{int(diff.total_seconds() / 60)}分钟前"
                elif diff.total_seconds() < 86400:
                    relative = f"{int(diff.total_seconds() / 3600)}小时前"
                else:
                    relative = f"{int(diff.total_seconds() / 86400)}天前"
            except Exception:
                relative = ""
        else:
            relative = ""

        collaborations.append({
            "id": run_id,
            "initiator": from_name,
            "executor": to_name,
            "task_summary": summary,
            "label": label,
            "status": status,
            "created_at": created_at,
            "ended_at": ended_at,
            "relative_time": relative,
        })

    # Sort by created_at desc, limit 50
    collaborations.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    collaborations = collaborations[:50]
    return {"collaborations": collaborations, "total": len(collaborations)}


@app.get("/api/blockers")
async def api_blockers():
    data = get_data()
    return data.get("blockers", [])


@app.get("/api/decisions")
async def api_decisions():
    data = get_data()
    return data.get("decisions", [])


@app.patch("/api/decisions/{decision_id}")
async def api_update_decision(decision_id: str, body: dict):
    """Update a decision (approve/reject)"""
    CYBER_TEAM_DIR = os.environ.get(
        "CYBER_TEAM_DIR",
        os.path.expanduser("~/.openclaw/workspace-can/cyber-team"),
    )

    # First get the decision to find the task_id
    data = get_data()
    decisions = data.get("decisions", [])
    target_task_id = None
    for d in decisions:
        if d.get("id") == decision_id:
            target_task_id = d.get("task_id")
            break

    if not target_task_id:
        return {"success": False, "error": "decision not found"}

    # Find and update the task file
    tasks_dir = os.path.join(CYBER_TEAM_DIR, "tasks")
    updated = False

    if os.path.exists(tasks_dir):
        # Look for the task file with matching task_id
        for filename in os.listdir(tasks_dir):
            if filename.endswith(".md"):
                filepath = os.path.join(tasks_dir, filename)
                content = open(filepath).read()

                # Check if this is the target task
                if target_task_id in filename:
                    # Add decision section if not exists, or update existing
                    new_status = body.get("decision_status", "decided")

                    # Check if 果爸决策 section exists
                    if "## 果爸决策" in content:
                        # Update existing section
                        lines = content.split("\n")
                        new_lines = []
                        in_decision_section = False
                        for line in lines:
                            if "## 果爸决策" in line:
                                in_decision_section = True
                                new_lines.append(line)
                            elif in_decision_section and line.startswith("## "):
                                # End of decision section
                                in_decision_section = False
                                new_lines.append(line)
                            elif in_decision_section:
                                if line.startswith("**决策结果**"):
                                    new_lines.append(f"**决策结果**: {new_status}")
                                elif line.startswith("**决策时间**"):
                                    from datetime import datetime, timezone
                                    new_lines.append(f"**决策时间**: {datetime.now(timezone.utc).isoformat()}")
                                else:
                                    pass  # Skip old content
                            else:
                                new_lines.append(line)
                        content = "\n".join(new_lines)
                    else:
                        # Add new decision section at end
                        from datetime import datetime, timezone
                        content += f"\n\n## 果爸决策\n\n"
                        content += f"- **决策结果**: {new_status}\n"
                        content += f"- **决策时间**: {datetime.now(timezone.utc).isoformat()}\n"

                    # Write back
                    with open(filepath, "w") as f:
                        f.write(content)
                    updated = True
                    break

    return {"success": updated, "decision_id": decision_id, "task_id": target_task_id}


def _get_cyber_team_dir():
    """Get the cyber-team directory path."""
    return os.environ.get(
        "CYBER_TEAM_DIR",
        os.path.expanduser("~/.openclaw/workspace-can/cyber-team"),
    )


def _update_decision_field(task_id: str, field: str, value: str):
    """Precisely update a field in the 果爸决策 table.

    Updates the markdown table row | field | old_value | to | field | value |.
    Also updates 决策时间 to now if provided.

    Returns (success: bool, filepath: str | None)
    """
    tasks_dir = os.path.join(_get_cyber_team_dir(), "tasks")
    if not os.path.exists(tasks_dir):
        return False, None

    for filename in os.listdir(tasks_dir):
        if filename.endswith(".md") and task_id in filename:
            filepath = os.path.join(tasks_dir, filename)
            try:
                with open(filepath, "r") as f:
                    content = f.read()

                lines = content.split("\n")
                new_lines = []
                in_decision_section = False
                updated = False

                for line in lines:
                    if "## 果爸决策" in line:
                        in_decision_section = True
                        new_lines.append(line)
                        continue
                    if in_decision_section and line.startswith("## "):
                        in_decision_section = False
                        new_lines.append(line)
                        continue
                    if in_decision_section:
                        # Match table row: | 最终决策 | value |
                        m = re.match(rf"^\|\s*{re.escape(field)}\s*\|\s*.+?\s*\|", line)
                        if m:
                            new_lines.append(f"| {field} | {value} |")
                            updated = True
                            continue
                        # Match bold-field: **决策时间**: value
                        m = re.match(rf"^\*\*{re.escape(field)}\*\*:\s*.+", line)
                        if m:
                            new_lines.append(f"**{field}**: {value}")
                            updated = True
                            continue
                    new_lines.append(line)

                if not updated:
                    return False, filepath

                with open(filepath, "w") as f:
                    f.write("\n".join(new_lines))

                return True, filepath
            except Exception as e:
                print(f"[task_update] error updating decision field {filepath}: {e}")
                return False, None

    return False, None


def _get_current_task_status(task_id: str) -> str:
    """Read the current status from the 任务执行 section of a task file."""
    tasks_dir = os.path.join(_get_cyber_team_dir(), "tasks")
    if not os.path.exists(tasks_dir):
        return ""

    for filename in os.listdir(tasks_dir):
        if filename.endswith(".md") and task_id in filename:
            filepath = os.path.join(tasks_dir, filename)
            try:
                with open(filepath, "r") as f:
                    content = f.read()

                lines = content.split("\n")
                in_execution_section = False
                for line in lines:
                    if "## 任务执行" in line:
                        in_execution_section = True
                        continue
                    if in_execution_section and line.startswith("## "):
                        break
                    if in_execution_section and "**状态**:" in line:
                        m = re.match(r"\*\*状态\*\*:\s*(.+)", line)
                        return m.group(1).strip() if m else ""
                return ""
            except Exception:
                return ""

    return ""


# State transition validation table
VALID_TRANSITIONS = {
    "pending-approval": {"in-progress", "rejected", "discussing"},
    "in-progress": {"pending-acceptance"},
    "pending-acceptance": {"completed", "in-progress"},
}


def _check_transition(task_id: str, new_status: str) -> tuple[bool, str]:
    """Check if status transition is valid. Returns (valid, error_msg)."""
    current = _get_current_task_status(task_id)
    if not current:
        return False, f"Task {task_id} not found or has no status"

    # Map display names to canonical form
    status_map = {
        "进行中": "in-progress", "in-progress": "in-progress",
        "待审批": "pending-approval", "pending-approval": "pending-approval",
        "待验收": "pending-acceptance", "pending-acceptance": "pending-acceptance",
        "已驳回": "rejected", "rejected": "rejected",
        "已完成": "completed", "completed": "completed",
        "讨论中": "discussing", "discussing": "discussing",
    }
    current_norm = status_map.get(current.lower().strip(), current.lower().strip())
    allowed = VALID_TRANSITIONS.get(current_norm, set())

    if new_status not in allowed:
        return False, f"Invalid transition: {current_norm} → {new_status}. Allowed: {allowed}"
    return True, ""


def _update_task_status_in_file(task_id: str, new_status: str, extra_content: str = "",
                                 target_sections: list[str] | None = None):
    """Update task status in specific sections of the .md file.

    Args:
        target_sections: Which sections to update. Default: ["任务执行"].
                         For accept, pass ["任务执行", "验收结果"].
    Returns (success: bool, filepath: str | None)
    """
    if target_sections is None:
        target_sections = ["任务执行"]

    tasks_dir = os.path.join(_get_cyber_team_dir(), "tasks")

    if not os.path.exists(tasks_dir):
        return False, None

    for filename in os.listdir(tasks_dir):
        if filename.endswith(".md") and task_id in filename:
            filepath = os.path.join(tasks_dir, filename)
            try:
                with open(filepath, "r") as f:
                    content = f.read()

                lines = content.split("\n")
                new_lines = []
                i = 0
                any_updated = False

                while i < len(lines):
                    line = lines[i]

                    # Check if this is a target section
                    matched_section = None
                    for sec in target_sections:
                        if f"## {sec}" in line:
                            matched_section = sec
                            break

                    if matched_section:
                        new_lines.append(line)
                        i += 1
                        # Process lines within this section until next ## heading
                        while i < len(lines) and not lines[i].startswith("## "):
                            if "**状态**:" in lines[i]:
                                new_lines.append(f"**状态**: {new_status}")
                                any_updated = True
                            else:
                                new_lines.append(lines[i])
                            i += 1
                        continue
                    else:
                        new_lines.append(line)
                        i += 1

                if not any_updated:
                    # Fallback: append status at end
                    new_lines.append(f"\n- **状态**: {new_status}")

                content = "\n".join(new_lines)

                if extra_content:
                    content += f"\n\n{extra_content}"

                with open(filepath, "w") as f:
                    f.write(content)

                return True, filepath
            except Exception as e:
                print(f"[task_update] error updating {filepath}: {e}")
                return False, None

    return False, None


@app.patch("/api/tasks/{task_id}/approve")
async def api_task_approve(task_id: str, body: dict = None):
    """Approve a pending-approval proposal -> in-progress."""
    # Validate state transition
    valid, err = _check_transition(task_id, "in-progress")
    if not valid:
        return {"success": False, "error": err}, 400

    # Update 任务执行 status to in-progress (only 任务执行 section)
    success, filepath = _update_task_status_in_file(task_id, "in-progress")

    if not success:
        return {"success": False, "error": f"Task {task_id} not found"}

    # Update decision table: 最终决策 → ✅同意, 决策时间 → now
    now = datetime.now(timezone.utc).isoformat()
    _update_decision_field(task_id, "最终决策", "✅同意")
    _update_decision_field(task_id, "决策时间", now)

    # Trigger data refresh
    await on_data_changed()

    return {
        "success": True,
        "task_id": task_id,
        "new_status": "in-progress",
        "action": "approved"
    }


@app.patch("/api/tasks/{task_id}/reject")
async def api_task_reject(task_id: str, body: dict = None):
    """Reject a pending-approval proposal -> rejected."""
    # Validate state transition
    valid, err = _check_transition(task_id, "rejected")
    if not valid:
        return {"success": False, "error": err}, 400

    success, filepath = _update_task_status_in_file(task_id, "rejected")

    if not success:
        return {"success": False, "error": f"Task {task_id} not found"}

    # Update decision table: 最终决策 → ❌驳回, 决策时间 → now
    now = datetime.now(timezone.utc).isoformat()
    _update_decision_field(task_id, "最终决策", "❌驳回")
    _update_decision_field(task_id, "决策时间", now)

    # Trigger data refresh
    await on_data_changed()

    return {
        "success": True,
        "task_id": task_id,
        "new_status": "rejected",
        "action": "rejected"
    }


@app.post("/api/tasks/{task_id}/discuss")
async def api_task_discuss(task_id: str, body: dict = None):
    """Mark a pending-approval proposal as discussing."""
    valid, err = _check_transition(task_id, "discussing")
    if not valid:
        return {"success": False, "error": err}, 400

    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).isoformat()
    extra_content = f"## 讨论标记\n\n- **状态**: 讨论中\n- **时间**: {timestamp}\n"

    success, filepath = _update_task_status_in_file(task_id, "discussing", extra_content)

    if not success:
        return {"success": False, "error": f"Task {task_id} not found"}

    await on_data_changed()

    return {
        "success": True,
        "task_id": task_id,
        "new_status": "discussing",
        "action": "discuss"
    }


@app.patch("/api/tasks/{task_id}/accept")
async def api_task_accept(task_id: str, body: dict = None):
    """Accept a pending-acceptance task -> completed."""
    valid, err = _check_transition(task_id, "completed")
    if not valid:
        return {"success": False, "error": err}, 400

    # Update both 任务执行 and 验收结果 sections
    success, filepath = _update_task_status_in_file(
        task_id, "completed", target_sections=["任务执行", "验收结果"])

    if not success:
        return {"success": False, "error": f"Task {task_id} not found"}

    await on_data_changed()

    return {
        "success": True,
        "task_id": task_id,
        "new_status": "completed",
        "action": "accepted"
    }


@app.patch("/api/tasks/{task_id}/request-revision")
async def api_task_request_revision(task_id: str, body: dict = None):
    """Request revision for a pending-acceptance task -> in-progress."""
    valid, err = _check_transition(task_id, "in-progress")
    if not valid:
        return {"success": False, "error": err}, 400

    success, filepath = _update_task_status_in_file(task_id, "in-progress")

    if not success:
        return {"success": False, "error": f"Task {task_id} not found"}

    await on_data_changed()

    return {
        "success": True,
        "task_id": task_id,
        "new_status": "in-progress",
        "action": "revision_requested"
    }


@app.get("/api/team")
async def api_team():
    data = get_data()
    return data.get("team", [])


@app.get("/api/registry")
async def api_registry():
    """Return the full cyber-team registry (role slots and assignments)."""
    registry_path = os.path.join(CYBER_TEAM_DIR, "registry.json")
    if os.path.exists(registry_path):
        with open(registry_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ─── Status API ────────────────────────────────────────────────────────────
@app.post("/api/status/report")
async def api_status_report(body: dict):
    """Employee submits a status report."""
    report = make_status_report(body)
    snapshot = update_snapshot(report)
    append_history(report)

    # Determine event type for WS broadcast
    event_type = "status_updated"
    if report.get("difficulty"):
        event_type = "difficulty_reported"
    elif report.get("needs_decision"):
        event_type = "decision_requested"

    await broadcast_status({
        "type": event_type,
        "payload": {
            "agent_id": report["agent_id"],
            "report": report,
            "panel": get_panel(),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "success": True,
        "report_id": report["report_id"],
        "next_report_at": snapshot.get("agents", {}).get(report["agent_id"], {}).get("next_report_at", ""),
    }


@app.get("/api/status/panel")
async def api_status_panel():
    """Get all employee real-time status."""
    return get_panel()


@app.get("/api/status/history")
async def api_status_history(
    agent_id: str = None,
    type: str = None,
    from_time: str = None,
    to_time: str = None,
    task_id: str = None,
    page: int = 1,
    limit: int = 20,
):
    """Get paginated status history with filters."""
    return get_history(
        agent_id=agent_id,
        type_filter=type,
        from_time=from_time,
        to_time=to_time,
        task_id=task_id,
        page=page,
        limit=min(limit, 100),
    )


@app.get("/api/status/{agent_id}")
async def api_status_agent(agent_id: str):
    """Get single employee status."""
    panel = get_panel()
    agent = next((a for a in panel["agents"] if a["agent_id"] == agent_id), None)
    if not agent:
        return {"error": f"Agent {agent_id} not found"}, 404
    return agent


@app.post("/api/status/difficulty")
async def api_status_difficulty(body: dict):
    """Specialized endpoint for reporting difficulties."""
    body["type"] = "difficulty"
    if not body.get("difficulty_level"):
        body["difficulty_level"] = body.get("severity", "minor")
    return await api_status_report(body)


# ─── WebSocket ───────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    if AUTH_ENABLED:
        cookie_token = ws.cookies.get("synapse_token", "")
        if cookie_token != SYNAPSE_TOKEN:
            await ws.send_text(json.dumps({"type": "error", "content": "Unauthorized"}))
            await ws.close(code=4401)
            return
    connected_clients.append(ws)
    print(f"[ws] connected, total clients: {len(connected_clients)}")
    sys.stdout.flush()

    try:
        # Send initial data
        data = get_data()
        payload = json.dumps({
            "type": "data_updated",
            "payload": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)
        print(f"[ws] sending {len(payload)} bytes")
        sys.stdout.flush()
        await ws.send_text(payload)
        print(f"[ws] sent successfully")
        sys.stdout.flush()

        # Keep connection alive
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                if msg == "ping":
                    await ws.send_text(json.dumps({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}))
            except asyncio.TimeoutError:
                # Send heartbeat
                await ws.send_text(json.dumps({
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
    except WebSocketDisconnect:
        print("[ws] client disconnected gracefully")
    except Exception as e:
        print(f"[ws] error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ws in connected_clients:
            connected_clients.remove(ws)
        print(f"[ws] cleaned up, remaining: {len(connected_clients)}")


@app.websocket("/ws/status")
async def websocket_status_endpoint(ws: WebSocket):
    """Dedicated WebSocket for status updates."""
    await ws.accept()
    status_clients.append(ws)
    print(f"[ws:status] connected, total: {len(status_clients)}")
    sys.stdout.flush()

    try:
        # Send current panel
        panel = get_panel()
        await ws.send_text(json.dumps({
            "type": "status_updated",
            "payload": {"panel": panel},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False))

        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                if msg == "ping":
                    await ws.send_text(json.dumps({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}))
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws:status] error: {e}")
    finally:
        if ws in status_clients:
            status_clients.remove(ws)
        print(f"[ws:status] cleaned up, remaining: {len(status_clients)}")


# ─── Static files ────────────────────────────────────────────────────────────
dist_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(dist_path):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=dist_path, html=True))
else:
    @app.get("/")
    async def root():
        return {"msg": "SynapseOS 2.0 API", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


