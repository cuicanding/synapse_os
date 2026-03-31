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
from asset_storage import query_assets, get_all_assets, get_domains, get_missions, get_assets_grouped
from activity_aggregator import get_agent_statuses, get_today_activities
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
SYNAPSE_TOKEN = os.environ.get("SYNAPSE_TOKEN", "")
AUTH_ENABLED = bool(SYNAPSE_TOKEN)
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
    tasks = data.get("tasks", [])
    tasks.sort(key=lambda t: t.get("_mtime", 0), reverse=True)
    return tasks

@app.get("/api/collaboration")
async def api_collaboration():
    """Return recent spawn collaboration records from runs.json."""
    from activity_aggregator import get_collaborations
    return get_collaborations()


@app.get("/api/agent-statuses")
async def api_agent_statuses():
    """Return all agent statuses auto-detected from STATUS.md."""
    return get_agent_statuses()


@app.get("/api/today-activities")
async def api_today_activities(agent_id: str = None):
    """Return today's activity auto-extracted from session files."""
    return get_today_activities(agent_id=agent_id)


@app.get("/api/daily-summary")
async def api_daily_summary(agent_id: str = None):
    """Return daily summary with tasks, collaborations, highlights."""
    from activity_aggregator import get_daily_summary
    return get_daily_summary(agent_id=agent_id)


@app.get("/api/latest-previews")
async def api_latest_previews():
    """Lightweight: latest highlight per agent for card display."""
    from activity_aggregator import get_latest_previews
    return get_latest_previews()


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
    """Read the current status from a task file.
    
    Priority:
    1. ## 任务执行 section内的 **状态**: or - **状态**:
    2. 全文件任意位置的 - **状态**: or **状态**: (fallback)
    """
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
                result = ""

                # 1. Check ## 任务执行 section
                in_execution_section = False
                for line in lines:
                    if "## 任务执行" in line:
                        in_execution_section = True
                        continue
                    if in_execution_section and line.startswith("## "):
                        break
                    if in_execution_section and "**状态**:" in line:
                        m = re.search(r"\*\*状态\*\*:\s*(.+)", line)
                        if m:
                            return m.group(1).strip().strip("`")

                # 2. Fallback: search entire file for status field
                for line in lines:
                    m = re.search(r"[-*]\s*\*\*状态\*\*:\s*(.+)", line)
                    if m:
                        return m.group(1).strip().strip("`")
                    # Also match bare **状态**: without list prefix
                    if not result:
                        m2 = re.match(r"\*\*状态\*\*:\s*(.+)", line)
                        if m2:
                            result = m2.group(1).strip()

                return result
            except Exception:
                return ""

    return ""


# State transition validation table
VALID_TRANSITIONS = {
    "pending-approval": {"in-progress", "rejected"},
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
                                # Preserve the line prefix (e.g., "- " or "- **状态**:")
                                line = lines[i]
                                m = re.match(r"^(\s*[-*]\s*)", line)
                                prefix = m.group(1) if m else ""
                                new_lines.append(f"{prefix}**状态**: {new_status}")
                                any_updated = True
                            else:
                                new_lines.append(lines[i])
                            i += 1
                        continue
                    else:
                        new_lines.append(line)
                        i += 1

                # Fallback: if no target sections found, search entire file
                if not any_updated:
                    has_target_section = any(f"## {sec}" in content for sec in target_sections)
                    if not has_target_section:
                        updated_lines = []
                        for line in lines:
                            if "**状态**:" in line:
                                m = re.match(r"^(\s*[-*]\s*)", line)
                                prefix = m.group(1) if m else ""
                                updated_lines.append(f"{prefix}**状态**: {new_status}")
                                any_updated = True
                            else:
                                updated_lines.append(line)
                        new_lines = updated_lines

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



@app.patch("/api/tasks/{task_id}/accept")
async def api_task_accept(task_id: str, body: dict = None):
    """Accept/complete a task -> completed."""
    valid, err = _check_transition(task_id, "completed")
    if not valid:
        return {"success": False, "error": err}, 400
    success, filepath = _update_task_status_in_file(task_id, "completed")
    if not success:
        return {"success": False, "error": f"Task {task_id} not found"}
    _update_decision_field(task_id, "决策时间", datetime.now(timezone.utc).isoformat())
    await on_data_changed()
    return {"success": True, "task_id": task_id, "new_status": "completed", "action": "accepted"}


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


# ─── Task Detail & Actions ──────────────────────────────────────────────────

@app.get("/api/tasks/{task_id}")
async def api_task_detail(task_id: str):
    """Return a single task's full data."""
    data = get_data()
    tasks = data.get("tasks", [])
    for t in tasks:
        if t.get("id") == task_id:
            return t
    return {"error": "Task not found"}, 404


@app.patch("/api/tasks/{task_id}/complete")
async def api_task_complete(task_id: str, body: dict = None):
    """Mark an in-progress task as complete -> pending-acceptance."""
    valid, err = _check_transition(task_id, "pending-acceptance")
    if not valid:
        return {"success": False, "error": err}, 400

    success, filepath = _update_task_status_in_file(task_id, "pending-acceptance")
    if not success:
        return {"success": False, "error": f"Task {task_id} not found"}

    title = _get_task_title(task_id)
    await broadcast_status({
        "type": "task_action_required",
        "task_id": task_id,
        "action": "accept",
        "title": title,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    await on_data_changed()
    return {"success": True, "task_id": task_id, "new_status": "pending-acceptance", "action": "completed"}



@app.patch("/api/tasks/{task_id}/abandon")
async def api_task_abandon(task_id: str, body: dict = None):
    """Abandon a failed task -> archived. Allowed from any non-archived status."""
    current = _get_current_task_status(task_id)
    if not current:
        return {"success": False, "error": f"Task {task_id} not found or has no status"}, 404
    if current in ("archived",):
        return {"success": False, "error": "Task already archived"}, 400
    success, filepath = _update_task_status_in_file(task_id, "archived")
    if not success:
        return {"success": False, "error": f"Task {task_id} not found"}
    await on_data_changed()
    return {"success": True, "task_id": task_id, "new_status": "archived", "action": "abandoned"}


@app.post("/api/tasks/{task_id}/add-artifact")
async def api_task_add_artifact(task_id: str, body: dict):
    """Add an artifact (deliverable) to a task file."""
    name = body.get("name", "").strip()
    path = body.get("path", "").strip()
    artifact_type = body.get("type", "DOC").strip()
    if not name or not path:
        return {"success": False, "error": "name and path are required"}, 400

    tasks_dir = os.path.join(_get_cyber_team_dir(), "tasks")
    if not os.path.exists(tasks_dir):
        return {"success": False, "error": "Tasks directory not found"}, 404

    target_file = None
    for filename in os.listdir(tasks_dir):
        if filename.endswith(".md") and task_id in filename:
            target_file = os.path.join(tasks_dir, filename)
            break

    if not target_file:
        return {"success": False, "error": f"Task {task_id} not found"}, 404

    try:
        with open(target_file, "r") as f:
            content = f.read()

        # Check if artifact section exists
        if "## 产出物" in content:
            # Append to existing section
            new_line = f"- **{name}** ({artifact_type}): `{path}`\n"
            # Insert before the next ## section or at end
            lines = content.split("\n")
            insert_idx = len(lines)
            for i, line in enumerate(lines):
                if line.startswith("## 产出物"):
                    # Find next ## section
                    for j in range(i + 1, len(lines)):
                        if lines[j].startswith("## ") and j > i:
                            insert_idx = j
                            break
                    break
            lines.insert(insert_idx, new_line)
            content = "\n".join(lines)
        else:
            # Create artifact section before the last section or at end
            new_section = f"\n## 产出物\n\n- **{name}** ({artifact_type}): `{path}`\n"
            content = content.rstrip() + new_section

        with open(target_file, "w") as f:
            f.write(content)

        await on_data_changed()
        return {"success": True, "task_id": task_id, "artifact": {"name": name, "path": path, "type": artifact_type}}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


# ─── File Content ────────────────────────────────────────────────────────────

@app.get("/api/file-content")
async def api_file_content(path: str):
    """Read and return file content for preview."""
    if not path:
        return {"error": "path is required"}, 400

    # Security: prevent directory traversal
    clean_path = os.path.normpath(path).lstrip("/")
    if ".." in clean_path:
        return {"error": "Invalid path"}, 400

    # Resolve against cyber-team directory
    base_dir = _get_cyber_team_dir()
    full_path = os.path.join(base_dir, clean_path)

    # Also try direct path if cyber-team prefix doesn't resolve
    if not os.path.exists(full_path):
        full_path = os.path.join(os.path.dirname(base_dir), clean_path)
    if not os.path.exists(full_path):
        full_path = clean_path

    if not os.path.exists(full_path):
        return {"error": f"File not found: {path}"}, 404
    if not os.path.isfile(full_path):
        return {"error": f"Not a file: {path}"}, 400

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "path": path}
    except Exception as e:
        return {"error": str(e)}, 500


# ─── Team Status MD ─────────────────────────────────────────────────────────

@app.get("/api/team/status-md")
async def api_team_status_md():
    """Return all agent status md contents from cyber-team/status/."""
    status_dir = os.path.join(_get_cyber_team_dir(), "status")
    result = {}
    if not os.path.exists(status_dir):
        return result
    for filename in os.listdir(status_dir):
        if filename.endswith(".md"):
            agent_id = filename.replace(".md", "")
            filepath = os.path.join(status_dir, filename)
            try:
                with open(filepath, "r") as f:
                    result[agent_id] = f.read()
            except Exception:
                pass
    return result


@app.get("/api/agents")
async def api_agents():
    """Return team.json as the single source of truth for agent registry."""
    team_path = os.path.join(_get_cyber_team_dir(), "team.json")
    if os.path.exists(team_path):
        with open(team_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    return {"agents": []}


@app.get("/api/agent-status")
async def api_agent_status():
    """Read each agent's status from cyber-team/status/{agentId}.md (single source of truth).
    Returns {agent_id: {work_status, current_task, last_update, raw}}."""
    result = {}
    status_dir = os.path.join(_get_cyber_team_dir(), "status")
    if not os.path.isdir(status_dir):
        return result
    for filename in os.listdir(status_dir):
        if not filename.endswith(".md") or filename == "README.md":
            continue
        agent_id = filename.replace(".md", "")
        filepath = os.path.join(status_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            last_update = ""
            work_status = "⚪ 未知"
            current_task = ""
            for line in content.split("\n"):
                line_s = line.strip()
                if line_s.startswith("更新时间:"):
                    last_update = line_s.split(":", 1)[1].strip()
                elif line_s.startswith("- **") and ("任务" in line_s or "方案" in line_s):
                    current_task = line_s.lstrip("- ").strip()
                    # Remove leading "- " and strip markdown bold
                    current_task = current_task.replace("**", "")
            if "空闲" in content:
                work_status = "🟢 空闲"
            elif "忙碌" in content or "进行中" in content:
                work_status = "🔴 忙碌"
            elif "完成" in content and "空闲" not in content:
                work_status = "🟢 空闲"
            result[agent_id] = {
                "agent_id": agent_id,
                "work_status": work_status,
                "current_task": current_task,
                "last_update": last_update,
                "raw": content,
            }
        except Exception:
            pass
    return result

def _get_task_title(task_id: str) -> str:
    """Get task title from tasks data."""
    data = get_data()
    for t in data.get("tasks", []):
        if t.get("id") == task_id:
            return t.get("title", task_id)
    return task_id


# ─── Assets ──────────────────────────────────────────────────────────────────

@app.get("/api/assets")
async def api_assets(
    domain: str = None,
    mission: str = None,
    asset_type: str = None,
    q: str = None,
    include_archived: bool = False,
):
    """Query assets with optional filters, return grouped format."""
    return get_assets_grouped(
        domain=domain or "",
        mission=mission or "",
        asset_type=asset_type or "",
        q=q or "",
        include_archived=include_archived,
    )


@app.get("/api/assets/domains")
async def api_asset_domains():
    return get_domains()


@app.get("/api/assets/missions")
async def api_asset_missions():
    return get_missions()


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


