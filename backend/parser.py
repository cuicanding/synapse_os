"""Parser for SynapseOS 2.0 — reads real cyber-team Markdown data."""
import os
import re
import frontmatter
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

# ─── Data directory ────────────────────────────────────────────────────────
CYBER_TEAM_DIR = os.environ.get(
    "CYBER_TEAM_DIR",
    os.path.expanduser("~/.openclaw/workspace-can/cyber-team"),
)


# ─── Data Classes ──────────────────────────────────────────────────────────
@dataclass
class Mission:
    id: str
    title: str
    status: str
    priority: str
    created_at: str
    content: str = ""
    description: str = ""
    goals: list = field(default_factory=list)
    team_overview: list = field(default_factory=list)  # [{role, member, duty}]
    milestones: list = field(default_factory=list)  # [{id, title, status}]
    task_ids: list = field(default_factory=list)
    # 使命驱动配置
    driver: str = ""           # 一号位，如 "Susan（苏珊）"
    workflow_interval: str = "" # 工作流周期，如 "12h"
    gate_rule: str = ""         # 门禁规则描述


@dataclass
class Task:
    id: str
    title: str
    status: str
    assignee: str
    priority: str
    created_at: str
    updated_at: str = ""
    content: str = ""
    mission_id: str = ""
    mission_title: str = ""
    decision_status: str = ""  # pending/decided/none
    decision_detail: str = ""
    has_blocker: bool = False
    blocker_reason: str = ""
    source_type: str = ""  # real-business / synapse-os
    creator: str = ""
    domain: str = ""
    iteration_round: str = ""     # e.g. "3" for 第3轮迭代
    iteration_driver: str = ""    # e.g. "Susan（苏珊）"
    _mtime: float = 0.0          # file modification timestamp
    proposal_content: str = ""    # 提案详情
    task_content: str = ""        # 完整任务描述（包括标题、详细描述、涉及文件等）
    judgment: str = ""            # 团队负责人判断说明


@dataclass
class Blocker:
    id: str
    title: str
    status: str
    priority: str
    assignee: str
    created_at: str
    content: str = ""
    reason: str = ""
    task_id: str = ""
    task_title: str = ""
    mission_id: str = ""


@dataclass
class Decision:
    id: str
    title: str
    status: str
    priority: str
    assignee: str
    created_at: str
    updated_at: str = ""
    content: str = ""
    decision_status: str = ""  # pending/decided
    decision_detail: str = ""
    source_of_truth: str = ""
    task_id: str = ""
    task_title: str = ""
    mission_id: str = ""
    domain: str = ""
    task_content: str = ""        # 完整任务描述
    proposal_content: str = ""    # 提案内容
    judgment_content: str = ""    # 团队负责人判断


@dataclass
class TeamMember:
    id: str
    name: str
    role: str
    status: str
    avatar: Optional[str] = None
    current_tasks: list = field(default_factory=list)
    domain: str = ""


# ─── Helpers ───────────────────────────────────────────────────────────────
def _strip(text: str) -> str:
    return text.strip() if text else ""


def _parse_table(content: str) -> list[dict]:
    """Parse markdown table into list of dicts using first row as header."""
    rows = []
    lines = [l for l in content.split("\n") if l.startswith("|")]
    if len(lines) < 2:
        return rows
    headers = [c.strip() for c in lines[0].strip("|").split("|")]
    for line in lines[2:]:  # skip separator
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= len(headers):
            rows.append(dict(zip(headers, cells[:len(headers)])))
    return rows


def _parse_field(field_name: str, content: str) -> str:
    """Extract a bold-field value from markdown, e.g. '- **状态**: in-progress' or '**状态**: in-progress'."""
    for line in content.split("\n"):
        # 匹配 - **字段**: 值 或 **字段**: 值
        m = re.match(rf"^\s*(?:-\s+)?\*\*{re.escape(field_name)}\*\*:\s*(.+)", line)
        if m:
            return _strip(m.group(1))
    return ""


def _parse_section(section_name: str, content: str) -> str:
    """Extract the content of a ## section (## Name ... until next ## or ---).
    Also handles ### sub-headers within the section."""
    lines = content.split("\n")
    result = []
    in_section = False
    for line in lines:
        # Match ## Section or ### Section (not deeper)
        stripped = line.lstrip()
        if re.match(r"^#{1,3}\s+" + re.escape(section_name), stripped):
            in_section = True
            continue
        if in_section:
            if re.match(r"^#{1,2}\s+(?!#)", stripped):
                break  # Next section of same or higher level
            if stripped == "---":
                break
            result.append(line)
    return "\n".join(result).strip()


# ─── Parsers ───────────────────────────────────────────────────────────────
def parse_mission(filepath: Path) -> Optional[Mission]:
    """Parse a mission markdown file."""
    if not filepath.exists():
        return None

    post = frontmatter.load(str(filepath))
    fm = dict(post.metadata)
    content = post.content

    sections = {}
    current = "header"
    current_lines = []
    for line in content.split("\n"):
        if line.startswith("## "):
            if current_lines:
                sections[current] = "\n".join(current_lines).strip()
                current_lines = []
            current = line.lstrip("# ").strip()
        else:
            current_lines.append(line)
    if current_lines:
        sections[current] = "\n".join(current_lines).strip()

    # Parse 基本信息 fields
    info_section = sections.get("基本信息", "")
    def _info_field(name: str) -> str:
        m = re.search(rf"\*\*{re.escape(name)}\*\*:\s*(.+)", info_section)
        return _strip(m.group(1)) if m else ""

    mission_id = _info_field("使命ID") or fm.get("使命ID", "") or filepath.stem
    mission_title = _info_field("名称") or fm.get("名称", "") or filepath.stem.replace("-", " ").title()
    mission_status = _info_field("状态") or fm.get("状态", "active")
    mission_created = _info_field("创建时间") or fm.get("创建时间", "")
    mission_desc = _info_field("描述") or ""

    # Extract goals
    goals = []
    goals_section = sections.get("使命目标", "")
    for line in goals_section.split("\n"):
        m = re.match(r"\d+\.\s+\*\*(.+?)\*\*\s*[-—]\s*(.+)", line)
        if m:
            goals.append({"title": m.group(1), "detail": m.group(2)})

    # Extract team overview
    team_overview = []
    team_section = sections.get("承担团队", "")
    team_rows = _parse_table(team_section)
    for row in team_rows:
        team_overview.append({
            "role": row.get("角色", ""),
            "member": row.get("赛博员工", ""),
            "duty": row.get("主要职责", ""),
        })

    # Extract milestones from 当前版本
    milestones = []
    version_section = sections.get("当前版本", "")
    for line in version_section.split("\n"):
        m = re.match(r"-\s+\*\*(.+?)\*\*:\s*(.+)", line)
        if m:
            milestones.append({
                "id": f"ms-{m.group(1).strip().lower().replace(' ', '-')}",
                "title": f"{m.group(1).strip()}: {m.group(2).strip()}",
                "status": "completed" if "已有" in m.group(2) else ("pending" if "规划中" in m.group(2) else "in-progress"),
            })

    # Extract driver config from 使命驱动配置 section
    driver = _parse_field("一号位", content) or ""
    workflow_interval = _parse_field("工作流周期", content) or ""
    gate_rule = _parse_field("门禁规则", content) or ""

    return Mission(
        id=mission_id,
        title=mission_title,
        status=mission_status,
        priority="high",
        created_at=mission_created,
        description=mission_desc,
        content=content,
        goals=goals,
        team_overview=team_overview,
        milestones=milestones,
        driver=driver,
        workflow_interval=workflow_interval,
        gate_rule=gate_rule,
    )


def parse_task(filepath: Path, mission_map: dict) -> Task:
    """Parse a task markdown file."""
    post = frontmatter.load(str(filepath))
    fm = dict(post.metadata)
    content = post.content

    # Extract title from 任务描述 section or 基本信息
    title = fm.get("标题", "")
    if not title:
        for line in content.split("\n"):
            m = re.search(r"\*\*标题\*\*:\s*(.+)", line)
            if m:
                title = _strip(m.group(1))
                break

    # Fallback: use first H1 heading (strip task ID prefix if present)
    if not title:
        for line in content.split("\n"):
            if line.startswith("# "):
                raw = _strip(line.lstrip("# "))
                # Strip "task-xxx：" prefix
                m = re.match(r"task-\S+[：:]\s*(.+)", raw)
                title = _strip(m.group(1)) if m else raw
                break

    # Parse all ## / ### sections first (needed for status parsing)
    sections = {}
    current_section = ""
    current_lines = []
    for line in content.split("\n"):
        if line.startswith("## ") or line.startswith("### "):
            if current_lines:
                sections[current_section] = "\n".join(current_lines).strip()
                current_lines = []
            current_section = line.lstrip("# ").strip()
        else:
            current_lines.append(line)
    if current_lines:
        sections[current_section] = "\n".join(current_lines).strip()

    # Status: 限定在 任务执行 section 内解析（兼容 任务信息 / 基本信息 section）
    exec_section = sections.get("任务执行", "") or sections.get("任务信息", "") or sections.get("基本信息", "")
    status = _parse_field("状态", exec_section) or fm.get("状态", "pending")
    # Normalize status
    status_map = {
        "pending": "pending", "进行中": "in-progress", "in-progress": "in-progress",
        "completed": "completed", "assigned": "assigned", "accepted": "accepted",
        "待审批": "pending-approval", "pending-approval": "pending-approval",
        "待验收": "pending-acceptance", "pending-acceptance": "pending-acceptance",
        "已驳回": "rejected", "rejected": "rejected",
        "discussing": "discussing", "讨论中": "discussing",
    }
    status = status_map.get(status.lower().strip().strip("`"), status.lower().strip().strip("`"))

    # sections dict already parsed above, used by multiple blocks below

    mission_id = _parse_field("使命ID", content) or fm.get("使命ID", "")
    # Clean up markdown backticks and parenthetical notes
    mission_id = mission_id.strip().strip("`")
    mission_id = re.sub(r"[（(].+[)）]", "", mission_id).strip()

    # Iteration fields (driven by mission's #1 person)
    iteration_round = _parse_field("迭代轮次", content) or fm.get("迭代轮次", "")
    iteration_driver = _parse_field("迭代驱动", content) or fm.get("迭代驱动", "")
    proposal_content = _parse_field("提案内容", content) or fm.get("提案内容", "")
    # If single-line parse fails, try section-level parse (## 提案内容)
    if not proposal_content:
        proposal_content = _parse_section("提案内容", content)
    # For iteration proposals, combine key sections into proposal_content
    if not proposal_content and (iteration_round or "迭代提案专用字段" in content):
        parts = []
        desc = sections.get("任务描述", "")
        if desc:
            parts.append(f"### 📋 任务描述\n{desc}")
        # Try multiple key patterns for value and priority
        value = sections.get("💎 价值点（必填）", "") or sections.get("💎 价值点", "")
        if value:
            parts.append(f"### 💎 价值点\n{value}")
        priority_reason = sections.get("🔥 优先级理由（必填）", "") or sections.get("🔥 优先级理由", "")
        if priority_reason:
            parts.append(f"### 🔥 优先级理由\n{priority_reason}")
        if parts:
            proposal_content = "\n\n".join(parts)
    proposal_status = status  # iteration status follows task status

    # Priority from team-lead section
    priority = "medium"
    priority_section = ""
    for line in content.split("\n"):
        if "优先级" in line:
            priority_section = line
            if "🔴" in line or "高" in line:
                priority = "high"
            elif "🟡" in line or "中" in line:
                priority = "medium"
            elif "🟢" in line or "低" in line:
                priority = "low"
            break

    # Decision status from 果爸决策 section
    decision_status = "none"
    decision_detail = ""
    source_of_truth = ""

    decision_section = sections.get("果爸决策", "")
    if decision_section:
        for line in decision_section.split("\n"):
            m = re.match(r"\|\s*最终决策\s*\|\s*(.+?)\s*\|", line)
            if m:
                val = m.group(1).strip()
                if "⏳" in val or "待" in val:
                    decision_status = "pending"
                elif "同意" in val or "✅" in val:
                    decision_status = "decided"
                elif "否定" in val or "❌" in val:
                    decision_status = "decided"
                decision_detail = val
                break
        for line in decision_section.split("\n"):
            m = re.match(r"\|\s*真相源\s*\|\s*(.+?)\s*\|", line)
            if m:
                source_of_truth = _strip(m.group(1))
                break

    # Source type — from 任务来源 section, skip header and delimiter rows
    source_type = ""
    source_section = sections.get("任务来源", "")
    if source_section:
        for line in source_section.split("\n"):
            # Skip header row (| 来源类型 | 说明 |) and delimiter (|---|)
            if re.match(r"\|\s*-+", line) or re.match(r"\|\s*来源类型", line):
                continue
            # Match data row with backtick value: | `synapse-os` | ... |
            m = re.match(r"\|\s*`([^`]+)`\s*\|", line)
            if m:
                source_type = _strip(m.group(1))
                break

    # Creator: 优先从 基本信息 section 读取（兼容老格式 任务信息 section）
    # basic_info 已在上面 assignee 部分定义，但这里确保顺序安全先获取
    basic_info = sections.get("基本信息", content) or sections.get("任务信息", content)
    creator = _parse_field("创建者", basic_info)
    if not creator:
        creator = _parse_field("创建人/负责人", basic_info)
    if not creator:
        creator = _parse_field("创建人", basic_info)
    # Clean creator name (extract name before parentheses)
    if creator:
        cm = re.match(r"([^（(]+)", creator)
        creator = _strip(cm.group(1)) if cm else creator
    # fallback: 全文搜索（保留兼容性）
    if not creator:
        for line in content.split("\n"):
            m = re.match(r"\s*[-*]\s*\*\*创建者\*\*:\s*(.+)", line)
            if not m:
                m = re.match(r"\*\*创建者\*\*:\s*(.+)", line)
            if m:
                creator = _strip(m.group(1))
                break
            m = re.match(r"\s*[-*]\s*\*\*创建人/负责人\*\*:\s*(.+)", line)
            if not m:
                m = re.match(r"\*\*创建人/负责人\*\*:\s*(.+)", line)
            if m:
                raw = _strip(m.group(1))
                cm = re.match(r"([^（(]+)", raw)
                creator = _strip(cm.group(1)) if cm else raw
                break
            m = re.match(r"\s*[-*]\s*\*\*创建人\*\*:\s*(.+)", line)
            if not m:
                m = re.match(r"\*\*创建人\*\*:\s*(.+)", line)
            if m:
                raw = _strip(m.group(1))
                cm = re.match(r"([^（(]+)", raw)
                creator = _strip(cm.group(1)) if cm else raw
                break

    # Updated at
    updated_at = _parse_field("更新时间", content) or fm.get("更新时间", "")
    # If updated_at has no time component, append file mtime
    if updated_at and re.match(r"^\d{4}-\d{2}-\d{2}$", updated_at.strip()):
        try:
            import time
            mtime_str = time.strftime("%H:%M", time.localtime(filepath.stat().st_mtime))
            updated_at = f"{updated_at.strip()} {mtime_str}"
        except Exception:
            pass
    # Created at - try from content first, fallback to frontmatter
    created_at_val = _parse_field("创建时间", content) or fm.get("创建时间", "")
    # If created_at has no time component, append file mtime
    if created_at_val and re.match(r"^\d{4}-\d{2}-\d{2}$", created_at_val.strip()):
        try:
            import time
            mtime_str = time.strftime("%H:%M", time.localtime(filepath.stat().st_mtime))
            created_at_val = f"{created_at_val.strip()} {mtime_str}"
        except Exception:
            pass
    # If created_at is still empty, fallback to file mtime
    if not created_at_val:
        try:
            import time
            created_at_val = time.strftime("%Y-%m-%d %H:%M", time.localtime(filepath.stat().st_mtime))
        except Exception:
            pass
    if not updated_at:
        updated_at = created_at_val

    # Assignee: 优先从 基本信息 section 的 执行者 字段读取，兼容老格式 任务信息 section
    basic_info = sections.get("基本信息", "") or sections.get("任务信息", "")
    assignee = _parse_field("执行者", basic_info)
    if not assignee:
        # fallback: 从创建者获取
        assignee = creator or "待分配"

    mission_title = mission_map.get(mission_id, {}).get("title", "") if mission_id else ""

    # Extract domain from task ID: task-infra-001 → infra, task-marketing-001 → marketing
    task_id_str = fm.get("任务ID", filepath.stem)
    domain = ""
    m = re.match(r"task-([a-z]+)-", task_id_str)
    if m:
        domain = m.group(1)

    # Parse full task description (任务描述 section)
    task_content = _parse_section("任务描述", content)

    # Parse team-lead judgment (判断说明 field)
    # Try both list-item format (- **判断说明**: ...) and inline format (**判断说明**: ...)
    judgment = _parse_field("判断说明", content)
    if not judgment:
        m = re.search(r"\*\*判断说明\*\*:\s*(.+)", content)
        if m:
            judgment = _strip(m.group(1))

    return Task(
        id=task_id_str,
        title=title or filepath.stem,
        status=status,
        assignee=assignee or creator or "待分配",
        priority=priority,
        created_at=created_at_val,
        updated_at=updated_at,
        content=content,
        mission_id=mission_id,
        mission_title=mission_title,
        decision_status=decision_status,
        decision_detail=decision_detail,
        source_type=source_type,
        creator=creator,
        domain=domain,
        iteration_round=iteration_round,
        iteration_driver=iteration_driver,
        proposal_content=proposal_content,
        task_content=task_content,
        judgment=judgment,
        _mtime=filepath.stat().st_mtime,
    )


def build_team(mission: Optional[Mission], tasks: list[Task]) -> list[TeamMember]:
    """Build team member list from mission team overview + task assignments."""
    members = {}

    # From mission team overview
    if mission and mission.team_overview:
        for entry in mission.team_overview:
            name = entry.get("member", "")
            if name and name not in members:
                members[name] = TeamMember(
                    id=f"member-{len(members)+1:02d}",
                    name=name,
                    role=entry.get("role", ""),
                    status="🟢 在线",  # Assume online for cyber employees
                    current_tasks=[],
                )

    # Ensure core members exist
    core_members = {
        "果爸": {"role": "董事长", "status": "🟢 在线"},
        "苏珊": {"role": "主设计师", "status": "🟢 在线"},
        "里德": {"role": "开发者", "status": "🟡 工作中"},
    }
    for name, info in core_members.items():
        if name not in members:
            members[name] = TeamMember(
                id=f"member-{len(members)+1:02d}",
                name=name,
                role=info["role"],
                status=info["status"],
                current_tasks=[],
            )

    # Assign tasks to members
    for task in tasks:
        assignees = task.assignee.split("+") if task.assignee else []
        for a in assignees:
            a = a.strip()
            if a in members and a != "待分配":
                members[a].current_tasks.append({
                    "id": task.id,
                    "title": task.title,
                    "status": task.status,
                })

    return list(members.values())


def build_blockers(tasks: list[Task]) -> list[Blocker]:
    """Derive blockers from tasks that are pending/assigned and waiting on decisions."""
    blockers = []
    for task in tasks:
        # Task with pending decision = potential blocker
        if task.decision_status == "pending":
            blockers.append(Blocker(
                id=f"blocker-{len(blockers)+1:03d}",
                title=f"待果爸决策: {task.title}",
                status="open",
                priority=task.priority,
                assignee=task.assignee,
                created_at=task.created_at,
                content=task.decision_detail,
                reason=f"任务 {task.id} 等待果爸最终决策才能推进",
                task_id=task.id,
                task_title=task.title,
                mission_id=task.mission_id,
            ))

    return blockers


def build_decisions(tasks: list[Task]) -> list[Decision]:
    """Derive decisions from tasks that have decision sections."""
    decisions = []
    for task in tasks:
        if task.decision_status in ("pending", "decided"):
            decisions.append(Decision(
                id=f"decision-{len(decisions)+1:03d}",
                title=task.title,
                status=task.decision_status,
                priority=task.priority,
                assignee="果爸",
                created_at=task.created_at,
                updated_at=task.updated_at,
                content=task.task_content,  # 完整任务描述
                decision_status=task.decision_status,
                decision_detail=task.decision_detail,
                source_of_truth="",
                task_id=task.id,
                task_title=task.title,
                mission_id=task.mission_id,
                task_content=task.task_content,
                proposal_content=task.proposal_content,
                judgment_content=task.judgment,
            ))

    return decisions


# ─── Main Entry Point ─────────────────────────────────────────────────────
def load_all() -> dict:
    """Load all data from cyber-team directory."""
    base = Path(CYBER_TEAM_DIR)

    # 1. Load missions (support multiple)
    mission_map = {}
    missions_list: list[Mission] = []
    mission_dir = base / "missions"
    if mission_dir.exists():
        for f in sorted(mission_dir.glob("*.md")):
            m = parse_mission(f)
            if m:
                mission_map[m.id] = asdict(m)
                missions_list.append(m)
    mission = missions_list[0] if missions_list else None

    # 2. Load tasks
    tasks = []
    task_dir = base / "tasks"
    if task_dir.exists():
        for f in sorted(task_dir.glob("task-*.md")):
            if f.name == "template.md":
                continue
            t = parse_task(f, mission_map)
            tasks.append(t)

    # 3. Link tasks to missions
    for m in missions_list:
        m.task_ids = [t.id for t in tasks if t.mission_id == m.id]

    # 4. Build blockers and decisions
    blockers = build_blockers(tasks)
    decisions = build_decisions(tasks)

    # 5. Build team
    team = build_team(mission, tasks)

    # 6. Add milestone tasks from missions
    for m in missions_list:
        if not m.milestones:
            m_tasks = [t for t in tasks if t.mission_id == m.id]
            in_progress = [t for t in m_tasks if t.status == "in-progress"]
            pending = [t for t in m_tasks if t.status == "pending"]
            if in_progress:
                m.milestones.append({
                    "id": "ms-current",
                    "title": f"当前迭代: {', '.join(t.title for t in in_progress[:2])}",
                    "status": "in-progress",
                })
            if pending:
                m.milestones.append({
                    "id": "ms-next",
                    "title": f"待启动: {len(pending)} 个任务等待推进",
                    "status": "pending",
                })

    return {
        "mission": asdict(missions_list[0]) if missions_list else None,
        "missions": [asdict(m) for m in missions_list],
        "tasks": [asdict(t) for t in tasks],
        "blockers": [asdict(b) for b in blockers],
        "decisions": [asdict(d) for d in decisions],
        "team": [asdict(m) for m in team],
    }


def reload() -> dict:
    """Alias for load_all."""
    return load_all()
