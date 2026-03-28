"""
status_reporter.py — 将 task 文件解析为实时状态报告

定时扫描 cyber-team/tasks/*.md，解析执行者+状态+困难+待决策，
生成状态快照并写入 status_current.json，使 Team 页面展示真实数据。
"""
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ─── 配置 ────────────────────────────────────────────────────────────────
CYBER_TEAM_DIR = os.environ.get(
    "CYBER_TEAM_DIR",
    os.path.expanduser("~/.openclaw/workspace-can/cyber-team"),
)
TASKS_DIR = os.path.join(CYBER_TEAM_DIR, "tasks")
SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "status_current.json")

# Agent 身份映射（从 registry assigned_to 推断）
# key: 中文名或英文名片段 → agent_id
AGENT_NAME_MAP = {
    "苏珊": "susan",
    "Susan": "susan",
    "sus": "susan",
    "里德": "reed",
    "Reed": "reed",
    "guoba": "guoba",
    "果爸": "guoba",
}

# Agent 元信息（名称+角色+域）
AGENT_META = {
    "susan": {"agent_name": "苏珊", "role": "产品设计师", "domain": "infrastructure"},
    "reed":  {"agent_name": "里德",  "role": "开发者",     "domain": "infrastructure"},
    "guoba": {"agent_name": "果爸",  "role": "董事长",     "domain": ""},
}

STALE_THRESHOLD_MINUTES = 5
REPORT_INTERVAL_MINUTES = 15


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def _task_state_to_progress(state: str) -> str:
    """任务状态 → progress 字段"""
    mapping = {
        "待启动": "idle",
        "规划中": "planning",
        "设计中": "planning",
        "进行中": "developing",
        "开发中": "developing",
        "测试中": "testing",
        "部署中": "deploying",
        "已完成": "completed",
        "已上线": "completed",
        "已挂起": "idle",
        "已取消": "completed",
        "已驳回": "rejected",
        "rejected": "rejected",
        "pending-approval": "pending-approval",
        "pending-acceptance": "pending-acceptance",
    }
    return mapping.get(state, "developing")


def _strip_md(text: str) -> str:
    """去掉 Markdown 粗体/斜体等标记"""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).strip()


def _extract_field(content: str, field: str) -> Optional[str]:
    """
    从 task 文件内容中提取字段，兼容新旧两种格式：
    - 旧格式（frontmatter 列表）: - **字段**: 值（前30行内）
    - 新格式（正文 bold）: **字段**: 值（不限位置，如 ## 任务描述 章节内）
    """
    # 旧格式：前30行的列表项 - **字段**: 值
    fm_lines = content.split("\n")[:30]
    fm_text = "\n".join(fm_lines)
    m = re.search(rf"- \*\*{re.escape(field)}\*\*[：:]\s*(.+?)(?:\n|$)", fm_text)
    if m:
        val = m.group(1).strip()
        if val and len(val) < 200:
            return val

    # 新格式：**字段**: 值（在任意位置，常见于 ## 任务描述 章节）
    m = re.search(rf"\*\*{re.escape(field)}\*\*[：:]\s*(.+?)(?:\n|$)", content)
    if m:
        val = m.group(1).strip()
        if val and len(val) < 300:
            return val
    return None


def _extract_executor(content: str) -> list[str]:
    """
    提取执行者/创建者列表，兼容新旧两种格式。
    - 旧格式（前30行 frontmatter 列表）: - **执行者**: xxx, - **创建者**: xxx
    - 新格式（正文）: **创建者**: 苏珊（位于 ## 任务来源 等章节）
    """
    fm_lines = content.split("\n")[:30]
    fm_text = "\n".join(fm_lines)
    executors = []

    # 旧格式
    for m in re.finditer(r"- \*\*(?:执行者|创建者)\*\*[：:]\s*(.+?)(?:\n|$)", fm_text):
        raw = m.group(1).strip()
        for n in re.split(r"[,，、]+", raw):
            n = _strip_md(n).strip()
            if n:
                executors.append(n)

    # 新格式：**创建者**: xxx（在正文中，不限位置）
    for m in re.finditer(r"\*\*(?:创建者|执行者)\*\*[：:]\s*(.+?)(?:\n|$)", content):
        raw = m.group(1).strip()
        for n in re.split(r"[,，、]+", raw):
            n = _strip_md(n).strip()
            if n and n not in executors:
                executors.append(n)

    return executors


def _parse_task_file(filepath: str) -> Optional[dict]:
    """解析单个 task 文件，返回结构化数据"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    task_id = os.path.basename(filepath).replace(".md", "")

    # 标题：优先从 **标题** 字段读取（H1 fallback 用于旧格式文件）
    title = _extract_field(content, "标题") or ""
    if not title:
        title_m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else task_id
    # 过滤掉章节名"任务数据"
    if title == "任务数据":
        title = task_id

    # 基本字段
    status = _extract_field(content, "状态") or "进行中"
    priority = _extract_field(content, "优先级") or ""

    # 执行者
    executors = _extract_executor(content)

    # 困难（blocking difficulty）
    difficulty = None
    difficulty_level = "none"
    diff_field = _extract_field(content, "困难") or _extract_field(content, "阻塞")
    if diff_field:
        difficulty = diff_field
        if any(kw in difficulty for kw in ["阻塞", "严重", "卡住", "无法", "失败", "blocking"]):
            difficulty_level = "blocking"
        else:
            difficulty_level = "minor"

    # 待决策（仅从 frontmatter 字段提取，不匹配正文内容）
    needs_decision = _extract_field(content, "待决策") or _extract_field(content, "需要决策")

    return {
        "task_id": task_id,
        "title": title,
        "status": status,
        "priority": priority,
        "executors": executors,
        "difficulty": difficulty,
        "difficulty_level": difficulty_level,
        "needs_decision": needs_decision,
    }


def _name_to_agent_id(name: str) -> Optional[str]:
    """将执行者名字转为 agent_id"""
    for key, aid in AGENT_NAME_MAP.items():
        if key in name:
            return aid
    # 模糊匹配：截取前两个字
    short = name[:2]
    for key, aid in AGENT_NAME_MAP.items():
        if key[:2] == short:
            return aid
    return None


def gather_all_status_reports() -> dict:
    """
    扫描所有 task 文件，为每个 agent 生成状态报告。
    返回 {"agents": {agent_id: status_report}}
    """
    if not os.path.exists(TASKS_DIR):
        return {"agents": {}}

    agents: dict = {}

    for filename in os.listdir(TASKS_DIR):
        if not filename.endswith(".md") or filename == "template.md":
            continue
        filepath = os.path.join(TASKS_DIR, filename)
        task = _parse_task_file(filepath)
        if not task:
            continue

        for exec_name in task["executors"]:
            aid = _name_to_agent_id(exec_name)
            if not aid:
                continue

            meta = AGENT_META.get(aid, {})
            now_iso = _now_iso()

            # 判断当前任务是否比已记录的任务更值得展示
            # 优先级：进行中 > 待启动 > 已驳回/已完成
            REJECTED_OR_DONE = {"已驳回", "rejected", "已完成", "completed", "已取消", "已挂起"}
            TERMINAL = REJECTED_OR_DONE | {"待启动"}

            new_progress = _task_state_to_progress(task["status"])
            existing = agents.get(aid)

            should_update = False
            if not existing:
                should_update = True
            elif task["status"] not in REJECTED_OR_DONE and existing.get("_task_status") in REJECTED_OR_DONE:
                # 当前任务是活跃的，已记录的是终态 → 覆盖
                should_update = True
            elif task["status"] not in TERMINAL and existing.get("_task_status") in TERMINAL:
                # 当前任务更活跃（进行中 vs 待启动等）→ 覆盖
                should_update = True
            elif task["status"] not in REJECTED_OR_DONE and existing.get("progress") == "rejected":
                # 当前任务活跃，已记录是 rejected → 覆盖
                should_update = True

            if should_update:
                agents[aid] = {
                    "agent_id": aid,
                    "agent_name": meta.get("agent_name", exec_name),
                    "role": meta.get("role", ""),
                    "domain": meta.get("domain", ""),
                    "current_task": task["title"],
                    "progress": new_progress,
                    "progress_detail": f"[{task['task_id']}] {task['status']}",
                    "difficulty": task["difficulty"],
                    "difficulty_level": task["difficulty_level"],
                    "needs_decision": task["needs_decision"],
                    "needs_help": None,
                    "task_id": task["task_id"],
                    "last_report_at": now_iso,
                    "next_report_at": (datetime.now(timezone(timedelta(hours=8))) + timedelta(minutes=REPORT_INTERVAL_MINUTES)).isoformat(),
                    "online_status": "online",
                    "is_stale": False,
                    "_task_status": task["status"],  # 内部用，不暴露给前端
                }
            else:
                # 多个任务：累加阻塞/决策信息（已有任务更优先时）
                if task["difficulty"] and not agents[aid].get("difficulty"):
                    agents[aid]["difficulty"] = task["difficulty"]
                    agents[aid]["difficulty_level"] = task["difficulty_level"]
                if task["needs_decision"] and not agents[aid].get("needs_decision"):
                    agents[aid]["needs_decision"] = task["needs_decision"]

    return {"agents": agents}


def write_snapshot(agents: dict) -> None:
    """将 agent 状态快照写入 status_current.json"""
    now_iso = _now_iso()
    snapshot = {
        "updated_at": now_iso,
        "agents": agents,
    }
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def run_report() -> dict:
    """
    执行一次完整状态采集，返回生成的 agents 字典。
    供 FastAPI 端点调用，或被定时任务调用。
    """
    result = gather_all_status_reports()
    if result["agents"]:
        write_snapshot(result["agents"])
    return result


if __name__ == "__main__":
    result = run_report()
    print(f"[status_reporter] generated reports for {len(result['agents'])} agents:")
    for aid, status in result["agents"].items():
        print(f"  {aid}: {status['current_task']} | progress={status['progress']} | difficulty={status['difficulty_level']} | needs_decision={bool(status['needs_decision'])}")
