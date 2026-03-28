"""
Asset storage for SynapseOS — reads and indexes all team assets.

Asset types: MS (milestone), FS (feature), AD (architecture decision),
             DS (design spec), RK (task record), RD (role definition)
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ─── Paths ────────────────────────────────────────────────────────────────
CYBER_TEAM_DIR = os.environ.get(
    "CYBER_TEAM_DIR",
    os.path.expanduser("~/.openclaw/workspace-can/cyber-team"),
)
ASSETS_DIR = os.path.join(CYBER_TEAM_DIR, "assets")
MISSIONS_DIR = os.path.join(CYBER_TEAM_DIR, "missions")
TASKS_DIR = os.path.join(CYBER_TEAM_DIR, "tasks")
ROLES_DIR = os.path.join(CYBER_TEAM_DIR, "roles")
REGISTRY_PATH = os.path.join(CYBER_TEAM_DIR, "registry.json")

# Type labels
TYPE_LABELS = {
    "MS": "里程碑",
    "FS": "功能点",
    "AD": "架构决策",
    "DS": "设计方案",
    "RK": "任务记录",
    "RD": "角色定义",
}

TYPE_EMOJI = {
    "MS": "📋",
    "FS": "⚡",
    "AD": "📐",
    "DS": "📝",
    "RK": "📄",
    "RD": "👤",
}


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-").lower()
    return text[:60]


def _strip_yaml_block(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter block from markdown content. Returns (metadata_dict, body)."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            import yaml
            try:
                meta = yaml.safe_load(parts[1]) or {}
            except Exception:
                meta = {}
            return meta, parts[2].lstrip("\n")
    return {}, content


def _generate_summary(title: str, content: str, asset_type: str) -> str:
    """Generate a 3-5 sentence summary from asset content using heuristics."""
    if not content:
        return f"{TYPE_LABELS.get(asset_type, '资产')}: {title}"

    # Strip markdown formatting
    text = re.sub(r"```[\s\S]*?```", "", content)
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\|[^|\n]+\|", "", text)
    text = re.sub(r"\n+", " ", text).strip()

    # Take first meaningful sentences (up to 300 chars)
    sentences = re.split(r"[。.!？?]", text)
    summary_parts = []
    char_count = 0
    for s in sentences:
        s = s.strip()
        if not s or len(s) < 5:
            continue
        summary_parts.append(s)
        char_count += len(s)
        if char_count > 200:
            break

    summary = "".join(summary_parts[:3])
    if not summary:
        summary = f"{TYPE_LABELS.get(asset_type, '资产')}: {title}"
    return summary[:300]


# ─── Asset ID helpers ──────────────────────────────────────────────────────

def _infer_asset_type_from_path(filepath: str) -> str:
    """Infer asset type from file path."""
    if "/designs/" in filepath or "/design/" in filepath:
        return "DS"
    if "/technical/" in filepath:
        return "AD"
    if "/plans/" in filepath:
        return "FS"
    if "/test-reports/" in filepath:
        return "RK"
    if "/roles/" in filepath:
        return "RD"
    return "DS"


def _infer_domain_from_path(filepath: str) -> str:
    """Infer domain from file path."""
    parts = filepath.split("/assets/")
    if len(parts) < 2:
        return "infrastructure"
    sub = parts[1].split("/")[0]
    domain_map = {
        "infrastructure": "infrastructure",
        "online": "online",
        "offline": "offline",
        "growth": "growth",
        "marketing": "marketing",
        "quant": "quant",
        "shared": "shared",
    }
    return domain_map.get(sub, sub)


def _infer_mission_from_content(content: str, domain: str) -> str:
    """Try to infer mission from content."""
    if "synapse-os" in content.lower() or "synapseos" in content.lower():
        return "synapse-os"
    if "金蟾" in content or "量化" in content:
        return "jinchan"
    # Default based on domain
    if domain in ("infrastructure", "online", "offline", "growth", "marketing"):
        return "synapse-os"
    if domain in ("quant",):
        return "jinchan"
    return ""


# ─── Parse individual files ────────────────────────────────────────────────

def _parse_asset_file(filepath: str, relative_path: str) -> Optional[dict]:
    """Parse a single asset file, return asset dict or None."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return None

    basename = os.path.basename(filepath).replace(".md", "")
    meta, body = _strip_yaml_block(raw)

    title = meta.get("title", "")
    if not title:
        # Try to extract from first H1
        m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        title = m.group(1).strip() if m else basename.replace("-", " ").title()

    asset_type = meta.get("type", "") or _infer_asset_type_from_path(filepath)
    domain = meta.get("domain", "") or _infer_domain_from_path(filepath)
    mission = meta.get("mission", "") or _infer_mission_from_content(body, domain)
    created_at = meta.get("created_at", "") or meta.get("date", "")
    archived = meta.get("archived", False)

    summary = meta.get("summary", "")
    if not summary:
        summary = _generate_summary(title, body, asset_type)

    return {
        "id": meta.get("id", "") or f"{asset_type.lower()}-{_slugify(title)}",
        "type": asset_type,
        "type_label": TYPE_LABELS.get(asset_type, asset_type),
        "type_emoji": TYPE_EMOJI.get(asset_type, "📦"),
        "title": title,
        "mission": mission,
        "domain": domain,
        "created_at": created_at,
        "file_mtime": os.path.getmtime(filepath),
        "archived": archived,
        "summary": summary,
        "content": body.strip(),
        "source_path": relative_path,
        "word_count": len(body.split()),
    }


def _parse_mission_milestones() -> list[dict]:
    """Parse missions/*.md files into MS-type assets."""
    assets = []
    if not os.path.exists(MISSIONS_DIR):
        return assets

    for fname in os.listdir(MISSIONS_DIR):
        if not fname.endswith(".md") or fname == "template.md":
            continue
        filepath = os.path.join(MISSIONS_DIR, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            continue

        mission_id = fname.replace(".md", "")
        meta, body = _strip_yaml_block(raw)

        # Extract title
        title = meta.get("title", "")
        if not title:
            m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = m.group(1).strip() if m else mission_id.replace("-", " ").title()

        created_at = meta.get("created_at", "") or meta.get("date", "")
        summary = meta.get("summary", "")
        if not summary:
            # Extract milestones from content
            summary = _generate_summary(title, body, "MS")

        assets.append({
            "id": f"ms-{mission_id}",
            "type": "MS",
            "type_label": "里程碑",
            "type_emoji": "📋",
            "title": title,
            "mission": mission_id,
            "domain": "infrastructure",  # default
            "created_at": created_at,
            "archived": False,
            "summary": summary,
            "content": body.strip(),
            "source_path": f"missions/{fname}",
            "word_count": len(body.split()),
        })

    return assets


def _parse_role_definitions() -> list[dict]:
    """Parse roles/*.md into RD-type assets."""
    assets = []
    if not os.path.exists(ROLES_DIR):
        return assets

    for fname in os.listdir(ROLES_DIR):
        if not fname.endswith(".md"):
            continue
        filepath = os.path.join(ROLES_DIR, fname)
        role_id = fname.replace(".md", "")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            continue

        meta, body = _strip_yaml_block(raw)
        title = meta.get("title", "") or role_id.replace("-", " ").title()
        created_at = meta.get("created_at", "") or ""
        summary = meta.get("summary", "")
        if not summary:
            summary = _generate_summary(title, body, "RD")

        assets.append({
            "id": f"rd-{role_id}",
            "type": "RD",
            "type_label": "角色定义",
            "type_emoji": "👤",
            "title": title,
            "mission": "",
            "domain": meta.get("domain", "shared"),
            "created_at": created_at,
            "archived": False,
            "summary": summary,
            "content": body.strip(),
            "source_path": f"roles/{fname}",
            "word_count": len(body.split()),
        })

    return assets


def _parse_design_and_technical_assets() -> list[dict]:
    """Parse assets/{domain}/{designs,technical}/*.md into AD/DS assets."""
    assets = []
    if not os.path.exists(ASSETS_DIR):
        return assets

    for root, dirs, files in os.walk(ASSETS_DIR):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            filepath = os.path.join(root, fname)
            rel = os.path.relpath(filepath, CYBER_TEAM_DIR)

            asset_type = _infer_asset_type_from_path(filepath)
            result = _parse_asset_file(filepath, rel)
            if result:
                assets.append(result)

    return assets


# ─── Domain + mission metadata ────────────────────────────────────────────

def get_domains() -> list[dict]:
    """Return list of domains with asset counts."""
    all_assets = get_all_assets(include_archived=True)
    counts: dict = {}
    for a in all_assets:
        d = a.get("domain", "unknown")
        t = a.get("type", "?")
        key = (d, t)
        counts[key] = counts.get(key, 0) + 1

    domain_order = ["infrastructure", "online", "offline", "growth", "marketing", "quant", "shared"]
    domain_labels = {
        "infrastructure": "基础设施域",
        "online": "在线业务域",
        "offline": "离线业务域",
        "growth": "增长域",
        "marketing": "市场域",
        "quant": "金蟾量化域",
        "shared": "共享资产",
    }

    result = []
    for domain in domain_order:
        type_counts = {}
        for (d, t), cnt in counts.items():
            if d == domain:
                type_counts[t] = cnt
        result.append({
            "id": domain,
            "label": domain_labels.get(domain, domain),
            "emoji": "🔧" if domain == "infrastructure" else "📦",
            "type_counts": type_counts,
            "total": sum(type_counts.values()),
        })

    return result


def get_missions() -> list[dict]:
    """Return list of missions."""
    missions = []
    if not os.path.exists(MISSIONS_DIR):
        return missions
    for fname in os.listdir(MISSIONS_DIR):
        if not fname.endswith(".md"):
            continue
        mission_id = fname.replace(".md", "")
        filepath = os.path.join(MISSIONS_DIR, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            continue
        meta, body = _strip_yaml_block(raw)
        title = meta.get("title", "")
        if not title:
            m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = m.group(1).strip() if m else mission_id
        missions.append({
            "id": mission_id,
            "title": title,
            "status": meta.get("status", "active"),
        })
    return missions


# ─── Main query function ──────────────────────────────────────────────────

def get_all_assets(include_archived: bool = False) -> list[dict]:
    """Load all assets from all sources."""
    assets = []
    assets.extend(_parse_mission_milestones())
    assets.extend(_parse_role_definitions())
    assets.extend(_parse_design_and_technical_assets())

    if not include_archived:
        assets = [a for a in assets if not a.get("archived", False)]

    return assets


def query_assets(
    mission: str = "",
    domain: str = "",
    asset_type: str = "",
    q: str = "",
    include_archived: bool = False,
) -> list[dict]:
    """Query assets with filters."""
    all_assets = get_all_assets(include_archived=include_archived)

    results = []
    for a in all_assets:
        if mission and a.get("mission") != mission:
            continue
        if domain and a.get("domain") != domain:
            continue
        if asset_type and a.get("type") != asset_type:
            continue
        if q:
            ql = q.lower()
            if ql not in a.get("title", "").lower() and ql not in a.get("summary", "").lower():
                continue
        results.append(a)

    # Sort by file_mtime desc (most recent first)
    results.sort(key=lambda a: a.get("file_mtime", 0), reverse=True)
    return results


# ─── Asset listing with domain grouping ──────────────────────────────────

def get_assets_grouped(
    mission: str = "",
    domain: str = "",
    asset_type: str = "",
    q: str = "",
    include_archived: bool = False,
) -> dict:
    """
    Return assets grouped by domain, with per-domain and per-type counts.
    Used by AssetCenter.svelte to render the domain nav + asset list.
    """
    assets = query_assets(
        mission=mission,
        domain=domain,
        asset_type=asset_type,
        q=q,
        include_archived=include_archived,
    )

    # Group by domain
    groups: dict = {}
    for a in assets:
        d = a.get("domain", "unknown")
        if d not in groups:
            groups[d] = []
        groups[d].append(a)

    # Build domain summary counts (unfiltered counts for nav)
    all_assets_full = get_all_assets(include_archived=True)
    domain_counts: dict = {}
    for a in all_assets_full:
        d = a.get("domain", "unknown")
        t = a.get("type", "?")
        if d not in domain_counts:
            domain_counts[d] = {}
        domain_counts[d][t] = domain_counts[d].get(t, 0) + 1

    domain_order = ["infrastructure", "online", "offline", "growth", "marketing", "quant", "shared"]
    domain_labels = {
        "infrastructure": "基础设施域", "online": "在线业务域",
        "offline": "离线业务域", "growth": "增长域",
        "marketing": "市场域", "quant": "金蟾量化域", "shared": "共享资产",
    }
    domain_emojis = {
        "infrastructure": "🔧", "online": "🌐", "offline": "🗄️",
        "growth": "📈", "marketing": "📣", "quant": "🦎", "shared": "📦",
    }

    ordered_groups = []
    for d in domain_order:
        if d not in groups:
            continue
        ordered_groups.append({
            "id": d,
            "label": domain_labels.get(d, d),
            "emoji": domain_emojis.get(d, "📦"),
            "assets": groups[d],
            "type_counts": domain_counts.get(d, {}),
        })

    return {
        "domains": ordered_groups,
        "total": len(assets),
        "missions": get_missions(),
        "domains_meta": {d: {"label": domain_labels.get(d, d), "emoji": domain_emojis.get(d, "📦"), "type_counts": domain_counts.get(d, {})} for d in domain_order},
    }
