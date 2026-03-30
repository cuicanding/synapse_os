<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { statusPanel, statusWsConnected, startStatusWs, stopStatusWs } from "../lib/status-ws";
  import { fetchStatusPanel, fetchStatusHistory, type AgentStatus, type StatusPanel, type StatusReport } from "../lib/api";
  import { showDifficultyModal, showHistorySidebar, statusDetailAgent } from "../lib/stores";
  import DifficultyModal from "./DifficultyModal.svelte";
  import StatusHistory from "./StatusHistory.svelte";

  let loading = true;
  let refreshTimer: ReturnType<typeof setInterval> | null = null;
  let collapsed: Record<string, boolean> = {};
  let agentStatusMd: Record<string, { work_status: string; current_task: string; last_update: string; raw: string }> = {};

  // Today modal state
  let showTodayModal = false;
  let todayModalAgent: RoleSlotCard | null = null;
  let todayRecords: StatusReport[] = [];
  let todayLoading = false;

  // Collaboration data
  interface Collaboration {
    id: string;
    initiator: string;
    executor: string;
    task_summary: string;
    status: string;
    created_at: string;
    relative_time?: string;
  }
  let collaborations: Collaboration[] = [];
  let showAllCollaborations = false;

  // Agent statuses from auto-aggregation API
  interface AgentAutoStatus {
    agent_id: string;
    name: string;
    emoji: string;
    role: string;
    status: string; // idle | busy | offline | unknown
    working_state: string;
    current_task: string;
    last_active: string;
    relative_active: string;
  }
  let agentAutoStatuses: Record<string, AgentAutoStatus> = {};

  // Today activities from auto-aggregation API
  interface TodayActivity {
    agent_id: string;
    agent_name: string;
    agent_emoji: string;
    role: string;
    type: string;
    content: string;
    timestamp: string;
    relative_time: string;
  }
  let todayActivities: TodayActivity[] = [];

  async function fetchCollaborations() {
    try {
      const r = await fetch("/api/collaboration");
      if (r.ok) {
        const data = await r.json();
        collaborations = data.collaborations || [];
      }
    } catch (e) {
      console.warn("[team] Failed to fetch collaborations:", e);
    }
  }

  // Latest activity per agent (for card preview)
  let latestActivity: Record<string, TodayActivity | null> = {};

  async function fetchTodayPreview() {
    try {
      const r = await fetch("/api/today-activities");
      if (r.ok) {
        const data = await r.json();
        const map: Record<string, TodayActivity | null> = {};
        for (const agent_id of AGENT_IDS) {
          map[agent_id] = null;
        }
        for (const a of (data.activities || [])) {
          if (!map[a.agent_id]) {
            map[a.agent_id] = a;
          }
        }
        latestActivity = map;
      }
    } catch (e) {
      console.warn("[team] Failed to fetch today preview:", e);
    }
  }

  const AGENT_IDS = ["main", "susan", "reed", "zhouhuajian", "renxianqi", "aniu", "zhouxingchi"];

  async function fetchAgentStatuses() {
    try {
      const r = await fetch("/api/agent-statuses");
      if (r.ok) {
        const data = await r.json();
        const map: Record<string, AgentAutoStatus> = {};
        for (const a of (data.agents || [])) {
          map[a.agent_id] = a;
        }
        agentAutoStatuses = map;
      }
    } catch (e) {
      console.warn("[team] Failed to fetch agent-statuses:", e);
    }
  }

  function formatRelativeTime(dateStr: string): string {
    if (!dateStr) return "—";
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "刚刚";
    if (diffMin < 60) return `${diffMin}分钟前`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}小时前`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay}天前`;
  }

  function collaborationStatusColor(status: string): string {
    switch (status) {
      case "completed": return "#10b981";
      case "running": return "#3b82f6";
      case "failed": return "#ef4444";
      default: return "#64748b";
    }
  }

  function collaborationStatusLabel(status: string): string {
    switch (status) {
      case "completed": return "已完成";
      case "running": return "进行中";
      case "failed": return "失败";
      default: return status;
    }
  }

  // ─── Domain 定义 ─────────────────────────────────────────────────────────
  const DOMAIN_META: Record<string, { name: string; emoji: string; color: string; desc: string }> = {
    infrastructure: { name: "基础设施域", emoji: "🔧", color: "#00E5FF", desc: "SynapseOS 等 AI-Native 管理工具" },
    online:         { name: "在线业务域", emoji: "🌐", color: "#22c55e", desc: "线上业务系统建设" },
    offline:        { name: "离线业务域", emoji: "🗄️", color: "#a78bfa", desc: "线下/批处理业务系统" },
    growth:         { name: "增长域",     emoji: "📈", color: "#f59e0b", desc: "用户增长与数据分析" },
    marketing:       { name: "市场域",     emoji: "📣", color: "#f472b6", desc: "市场推广与投放" },
    quant:           { name: "金蟾量化团队", emoji: "🦎", color: "#f59e0b", desc: "量化策略研究、开发与数据基建" },
  };

  // ─── 从 team.json 加载员工列表（唯一真理源） ─────────────────────────────
  let teamAgents: any[] = [];

  async function loadTeamAgents() {
    try {
      const r = await fetch("/api/agents");
      if (r.ok) {
        const data = await r.json();
        teamAgents = data.agents || [];
      }
    } catch (e) {
      console.warn("[team] team.json load failed:", e);
    }
  }

  // ─── 从 STATUS.md 读取员工真实状态 ─────────────────────────────────────
  async function loadAgentStatus() {
    try {
      const r = await fetch("/api/agent-status");
      if (r.ok) {
        agentStatusMd = await r.json();
      }
    } catch (e) {
      console.warn("[team] agent-status load failed:", e);
    }
  }

  // ─── 从 status panel 拿实时状态 ────────────────────────────────────────
  async function refresh() {
    try {
      const panel = await fetchStatusPanel();
      console.log("[team] panel agents:", panel?.agents?.length, panel?.agents?.map(a => `${a.agent_id}:${a.agent_name}`));
      statusPanel.set(panel);
    } catch (e) {
      console.error("[team] refresh failed:", e);
    } finally {
      loading = false;
    }
  }

  // ─── 合并 registry slots + status panel ─────────────────────────────────
  // 支持两种匹配：agent_id 精确匹配，或 agent_name 去掉括号后匹配
  $: reportedMap = ((): Record<string, AgentStatus> => {
    const map: Record<string, AgentStatus> = {};
    const agents = $statusPanel?.agents || [];
    console.log("[team] building reportedMap, agents count:", agents.length);
    for (const a of agents) {
      if (a.agent_id) map[a.agent_id] = a;
      if (a.agent_name) {
        const plain = a.agent_name.replace(/[（(].*[）)]/g, "").trim();
        map[plain] = a;
        map[a.agent_name] = a;
      }
    }
    console.log("[team] reportedMap keys:", Object.keys(map));
    return map;
  })();

  // 构建完整角色卡片列表
  interface RoleSlotCard {
    roleKey: string;
    roleLabel: string;
    domain: string;
    agentName: string | null;      // registry assigned_to (string or string[])
    agentNames: string[];         // normalized list of names
    agentId: string | null;        // registry agentId
    status: AgentStatus | null;     // 真实上报状态（匹配 agent_id）
    isStale: boolean;
    onlineStatus: "online" | "stale" | "unassigned";
    progress: string;
    progressDetail: string;
    difficultyLevel: string;
    difficulty: string | null;
    needsDecision: string | null;
    currentTask: string;
    lastReportAt: string | null;
    statusMd: { work_status: string; current_task: string; last_update: string; raw: string } | null;
  }

  // 名字匹配：assigned_to 可能是 "Reed（里德）" 或 "苏珊"，
  // agent_name 可能是 "里德" 或 "苏珊"，需要双向包含检查
  function nameMatches(assignedTo: any, agentName: string | null): boolean {
    if (!assignedTo || !agentName) return false;
    // If assignedTo is an array, check each element
    if (Array.isArray(assignedTo)) {
      return assignedTo.some(name => nameMatches(name, agentName));
    }
    if (typeof assignedTo !== "string") return false;
    // Complete match
    if (assignedTo === agentName) return true;
    // Includes check (handle "Reed（里德）" vs "里德")
    if (assignedTo.includes(agentName) || agentName.includes(assignedTo)) return true;
    // Remove paren content and compare
    const withoutParen = assignedTo.replace(/[（(].*[）)]/g, "");
    if (withoutParen === agentName) return true;
    return false;
  }

  // Normalize assigned_to to string[] (supports single string or array)
  function normalizeNames(assignedTo: any): string[] {
    if (!assignedTo) return [];
    if (Array.isArray(assignedTo)) return assignedTo;
    if (typeof assignedTo === "string") return [assignedTo];
    return [];
  }

  // Format names for display: ["任贤齐", "阿牛"] → "任贤齐、阿牛"
  function formatNames(names: string[]): string {
    return names.join("、");
  }

  // 角色标签中文映射
  const ROLE_LABELS: Record<string, string> = {
    "architect": "架构师",
    "developer": "开发者",
    "product-designer": "产品设计师",
    "quant-analyst": "策略分析师",
    "quant-developer": "策略开发师",
    "quant-data-engineer": "策略数据工程师",
  };

  $: allCards = ((): RoleSlotCard[] => {
    const cards: RoleSlotCard[] = [];
    for (const agent of teamAgents) {
      const agentId = agent.id;
      const domains: string[] = agent.domains || [];
      const roles: string[] = agent.roles || [];

      // 匹配 status panel
      let reported: AgentStatus | null = null;
      if (reportedMap[agentId]) {
        reported = reportedMap[agentId];
      } else {
        const agents = $statusPanel?.agents || [];
        for (const a of agents) {
          if (a.agent_name && (a.agent_id === agentId || nameMatches(agent.name, a.agent_name))) {
            reported = a;
            break;
          }
        }
      }

      let onlineStatus: RoleSlotCard["onlineStatus"] = "unassigned";
      if (reported) {
        onlineStatus = reported.is_stale ? "stale" : "online";
      } else if (agent.type === "openclaw") {
        onlineStatus = "stale";
      }

      // 每个 domain × role 组合生成一张卡片
      for (const domain of domains) {
        for (const role of roles) {
          cards.push({
            roleKey: `${domain}-${role}`,
            roleLabel: ROLE_LABELS[role] || role,
            domain,
            agentName: agent.fullName || agent.name,
            agentNames: [agent.name],
            agentId,
            status: reported,
            isStale: onlineStatus === "stale",
            onlineStatus,
            progress: reported?.progress || "idle",
            progressDetail: reported?.progress_detail || "",
            difficultyLevel: reported?.difficulty_level || "none",
            difficulty: reported?.difficulty || null,
            needsDecision: reported?.needs_decision || null,
            currentTask: reported?.current_task || "",
            lastReportAt: reported?.last_report_at || null,
            statusMd: agentId ? (agentStatusMd[agentId] || null) : null,
          });
        }
      }
    }
    return cards;
  })();

  // 按 domain 分组
  $: domainGroups = (() => {
    const groups: Record<string, RoleSlotCard[]> = {};
    for (const card of allCards) {
      if (!groups[card.domain]) groups[card.domain] = [];
      groups[card.domain].push(card);
    }
    return groups;
  })();

  // Domain 排序：infrastructure 第一，其他按字母
  $: domainOrder = [
    "infrastructure",
    ...Object.keys(domainGroups)
      .filter((d) => d !== "infrastructure" && d !== "quant")
      .sort(),
    "quant",
  ].filter((d) => domainGroups[d]);

  // ─── 统计 ───────────────────────────────────────────────────────────────
  $: totalSlots = allCards.length;
  $: assignedSlots = allCards.filter((c) => c.agentName).length;
  $: onlineSlots = allCards.filter((c) => c.onlineStatus === "online").length;
  $: staleSlots  = allCards.filter((c) => c.onlineStatus === "stale").length;
  $: unassignedSlots = allCards.filter((c) => c.onlineStatus === "unassigned").length;
  $: blockingSlots = allCards.filter((c) => c.difficultyLevel === "blocking").length;
  $: decisionSlots = allCards.filter((c) => c.needsDecision).length;

  // ─── Helpers ─────────────────────────────────────────────────────────────
  function timeAgo(iso: string | null): string {
    if (!iso) return "—";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "刚刚";
    if (mins < 60) return `${mins}分钟前`;
    const hours = Math.floor(mins / 60);
    return `${hours}小时前`;
  }

  function progressLabel(p: string): string {
    const m: Record<string, string> = {
      planning: "📋 规划中",
      developing: "🔨 开发中",
      testing: "🧪 测试中",
      deploying: "🚀 部署中",
      completed: "✅ 已完成",
      idle: "☕ 空闲",
    };
    return m[p] || p;
  }

  function initials(name: string | null): string {
    if (!name) return "??";
    const parts = name.replace(/[^\u4e00-\u9fa5a-zA-Z]/g, "").split("");
    return parts.length >= 2 ? parts.slice(0, 2).join("") : (parts[0]?.toUpperCase() || "?");
  }

  function openHistory(agentId: string) {
    statusDetailAgent.set(agentId);
    showHistorySidebar.set(true);
  }

  function openDifficulty(agentId: string) {
    statusDetailAgent.set(agentId);
    showDifficultyModal.set(true);
  }

  // Get latest activity text from card status
  function getLatestActivity(card: RoleSlotCard): string {
    if (!card.status) return "暂无动态";
    if (card.status.progress_detail) return card.status.progress_detail;
    if (card.status.needs_help) return `需求: ${card.status.needs_help}`;
    if (card.status.difficulty) return `困难: ${card.status.difficulty}`;
    if (card.status.needs_decision) return `待决策: ${card.status.needs_decision}`;
    return "暂无动态";
  }

  // Open today modal and fetch activities from auto-aggregation API
  async function openTodayModal(card: RoleSlotCard) {
    if (!card.agentId) return;
    todayModalAgent = card;
    showTodayModal = true;
    todayLoading = true;
    todayActivities = [];

    try {
      const r = await fetch(`/api/today-activities?agent_id=${card.agentId}`);
      if (r.ok) {
        const data = await r.json();
        todayActivities = data.activities || [];
      }
    } catch (e) {
      console.error("[team] Failed to fetch today activities:", e);
    } finally {
      todayLoading = false;
    }
  }

  function closeTodayModal() {
    showTodayModal = false;
    todayModalAgent = null;
    todayRecords = [];
  }

  function formatTime(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }

  function getRecordTypeIcon(type: string): string {
    switch (type) {
      case "difficulty": return "🚨";
      case "decision": return "🔔";
      default: return "📋";
    }
  }

  onMount(() => {
    startStatusWs();
    loadTeamAgents();
    loadAgentStatus();
    refresh();
    fetchCollaborations();
    fetchAgentStatuses();
    fetchTodayPreview();
    refreshTimer = setInterval(() => { refresh(); loadTeamAgents(); loadAgentStatus(); fetchCollaborations(); fetchAgentStatuses(); fetchTodayPreview(); }, 30000);
  });

  onDestroy(() => {
    if (refreshTimer) clearInterval(refreshTimer);
  });
</script>

<!-- Difficulty modal -->
<DifficultyModal />
<StatusHistory />

<div class="page-enter space-y-6">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <div>
      <h1 class="font-orbitron text-2xl font-bold neon-cyan flex items-center gap-2">
        <span>⬟</span> 团队状态
      </h1>
      <p class="text-txt-secondary text-sm mt-1 font-chinese">
        赛博团队角色总览 · {assignedSlots}/{totalSlots} 已分配
      </p>
    </div>

    <div class="flex items-center gap-3 flex-wrap" style="overflow-x:auto;">
      <!-- WS 连接状态 -->
      <div class="glass-card px-3 py-1.5 flex items-center gap-2 flex-shrink-0">
        <span class="w-2 h-2 rounded-full {$statusWsConnected ? 'bg-cyber-green pulse-glow' : 'bg-cyber-red'}"></span>
        <span class="text-xs font-mono text-txt-secondary">{$statusWsConnected ? '实时' : '离线'}</span>
      </div>

      <!-- 统计 pill -->
      {#if !loading}
        <div class="glass-card px-4 py-2 flex items-center gap-3 flex-wrap flex-shrink-0">
          <span class="flex items-center gap-1 text-xs font-mono">
            <span class="w-1.5 h-1.5 rounded-full bg-cyber-cyan"></span>
            <span class="text-cyber-cyan font-bold">{assignedSlots}</span> 已分配
          </span>
          <span class="text-white/10">|</span>
          <span class="flex items-center gap-1 text-xs font-mono">
            <span class="w-1.5 h-1.5 rounded-full bg-cyber-green"></span>
            <span class="text-cyber-green font-bold">{onlineSlots}</span> 在线
          </span>
          {#if staleSlots > 0}
            <span class="text-white/10">|</span>
            <span class="flex items-center gap-1 text-xs font-mono">
              <span class="w-1.5 h-1.5 rounded-full bg-cyber-amber"></span>
              <span class="text-cyber-amber font-bold">{staleSlots}</span> 离线
            </span>
          {/if}
          {#if unassignedSlots > 0}
            <span class="text-white/10">|</span>
            <span class="flex items-center gap-1 text-xs font-mono">
              <span class="w-1.5 h-1.5 rounded-full bg-txt-secondary/40"></span>
              <span class="text-txt-secondary font-bold">{unassignedSlots}</span> 空缺
            </span>
          {/if}
          {#if blockingSlots > 0}
            <span class="text-white/10">|</span>
            <span class="flex items-center gap-1 text-xs font-mono">
              <span class="w-1.5 h-1.5 rounded-full bg-cyber-red"></span>
              <span class="text-cyber-red font-bold">{blockingSlots}</span> 阻塞
            </span>
          {/if}
          {#if decisionSlots > 0}
            <span class="text-white/10">|</span>
            <span class="flex items-center gap-1 text-xs font-mono">
              <span class="w-1.5 h-1.5 rounded-full bg-cyber-amber"></span>
              <span class="text-cyber-amber font-bold">{decisionSlots}</span> 待决策
            </span>
          {/if}
          {#if staleSlots === 0 && unassignedSlots === 0 && blockingSlots === 0}
            <span class="text-xs font-mono text-cyber-green">✨ 运转正常</span>
          {/if}
        </div>
      {/if}

      <button
        onclick={refresh}
        class="glass-card px-3 py-2 text-xs font-mono text-txt-secondary hover:text-cyber-cyan transition-colors"
      >
        ↻ 刷新
      </button>
    </div>
  </div>

  <!-- Domain 分组展示 -->
  {#if loading}
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      {#each Array(6) as _}
        <div class="glass-card p-5 h-40 animate-pulse bg-bg-mid/30"></div>
      {/each}
    </div>
  {:else}
    <!-- Collaboration Timeline (compact single-line list) -->
    {#if collaborations.length > 0}
      <div class="glass-card p-4 mb-4">
        <h3 class="font-rajdhani text-sm font-bold text-txt-primary flex items-center gap-2 mb-3">
          <span>🔄</span> 协作动态
        </h3>
        <div class="space-y-1">
          {#each (showAllCollaborations ? collaborations : collaborations.slice(0, 10)) as collab}
            <div class="flex items-center gap-2 text-xs font-mono py-1 px-2 rounded hover:bg-white/5 transition-colors">
              <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" style="background-color: {collaborationStatusColor(collab.status)}"></span>
              <span class="text-cyber-cyan truncate max-w-[100px]">{collab.initiator}</span>
              <span class="text-txt-secondary/40">→</span>
              <span class="text-cyber-violet truncate max-w-[100px]">{collab.executor}</span>
              <span class="text-txt-secondary flex-shrink-0">|</span>
              <span class="text-txt-primary truncate flex-1">{collab.task_summary?.slice(0, 40) || '—'}{collab.task_summary?.length > 40 ? '…' : ''}</span>
              <span class="px-1 py-0.5 rounded flex-shrink-0" style="background-color: {collaborationStatusColor(collab.status)}15; color: {collaborationStatusColor(collab.status)}">{collaborationStatusLabel(collab.status)}</span>
              <span class="text-txt-secondary/50 flex-shrink-0">{formatRelativeTime(collab.created_at)}</span>
            </div>
          {/each}
        </div>
        {#if collaborations.length > 10}
          <button
            class="text-xs text-cyber-cyan hover:underline mt-2"
            on:click={() => showAllCollaborations = !showAllCollaborations}
          >
            {showAllCollaborations ? '收起' : `查看全部 (${collaborations.length})`}
          </button>
        {/if}
      </div>
    {/if}

    {#each domainOrder as domain}
      {@const meta = DOMAIN_META[domain] || { name: domain, emoji: "📦", color: "#64748b", desc: "" }}
      {@const cards = domainGroups[domain] || []}
      {@const collapsed_d = collapsed[domain] ?? false}

      <div class="glass-card p-5">
        <!-- Domain Header -->
        <button
          class="w-full flex items-center gap-3 mb-4 group"
          onclick={() => collapsed[domain] = !collapsed_d}
        >
          <span class="text-2xl">{meta.emoji}</span>
          <div class="flex-1 text-left">
            <span class="font-rajdhani text-lg font-bold" style="color:{meta.color}">
              {meta.name}
            </span>
            <span class="text-xs text-txt-secondary ml-2">（{cards.length}个角色）</span>
            {#if meta.desc}
              <p class="text-xs text-txt-secondary/60 mt-0.5 font-chinese">{meta.desc}</p>
            {/if}
          </div>
          <!-- 域内小统计 -->
          <div class="flex items-center gap-2 mr-2 flex-shrink-0">
            {#each cards as card}
              {@const dotColor = card.onlineStatus === "online" ? "bg-cyber-green" : card.onlineStatus === "stale" ? "bg-cyber-amber" : "bg-white/10"}
              <span class="w-2 h-2 rounded-full {dotColor}" title="{card.agentName || '空缺'}: {card.onlineStatus}"></span>
            {/each}
          </div>
          <span class="text-txt-secondary text-sm transition-transform {collapsed_d ? '' : 'rotate-90'}">
            ▶
          </span>
        </button>

        <!-- Role Cards Grid -->
        {#if !collapsed_d}
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {#each cards as card (card.roleKey + '-' + card.agentId)}
              {@const isUnassigned = card.onlineStatus === "unassigned"}
              {@const isStale = card.onlineStatus === "stale"}
              {@const isOnline = card.onlineStatus === "online"}
              {@const hasBlocking = card.difficultyLevel === "blocking"}
              {@const hasDecision = !!card.needsDecision}
              <!-- 角色卡片 -->
              <div
                class="relative rounded-xl border transition-all hover:scale-[1.01] p-4
                  {isOnline && !hasBlocking && !hasDecision ? 'border-cyber-cyan/20' : ''}
                  {isStale && !hasBlocking ? 'border-cyber-amber/40' : ''}
                  {hasBlocking ? 'border-cyber-red/50 bg-cyber-red/5' : ''}
                  {hasDecision && !hasBlocking ? 'border-cyber-amber/30 bg-cyber-amber/5' : ''}
                  {isUnassigned ? 'border-white/5 bg-bg-mid/50' : ''}"
              >
                <!-- 状态 dot -->
                <div class="absolute top-3 right-3 flex items-center gap-1.5">
                  {#if isOnline}
                    <span class="w-2 h-2 rounded-full bg-cyber-green pulse-glow"></span>
                  {:else if isStale}
                    <span class="w-2 h-2 rounded-full bg-cyber-amber" title="离线"></span>
                  {:else}
                    <span class="w-2 h-2 rounded-full bg-white/10" title="未分配"></span>
                  {/if}
                </div>

                <!-- 角色标签 -->
                <div class="text-xs font-mono text-txt-secondary mb-2">{card.roleLabel}</div>

                <!-- 人员信息 -->
                {#if card.agentNames.length > 0}
                  {#each card.agentNames as name, ni}
                    {@const autoStatus = card.agentId ? agentAutoStatuses[card.agentId] : null}
                    {@const statusLight = !autoStatus ? '⚪' : autoStatus.status === 'busy' ? '🔴' : autoStatus.status === 'idle' ? '🟢' : autoStatus.status === 'offline' ? '🌑' : '⚪'}
                    <div class="flex items-center gap-2 {ni > 0 ? 'mt-1.5 pt-1.5 border-t border-white/5' : 'mb-2'}">
                      <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500/60 to-amber-700/60 flex items-center justify-center">
                        <span class="font-orbitron text-xs font-bold text-txt-primary">
                          {initials(name)}
                        </span>
                      </div>
                      <div class="flex-1 min-w-0">
                        <p class="text-sm font-semibold text-txt-primary truncate">{name} {statusLight}</p>
                        {#if autoStatus && autoStatus.role}
                          <p class="text-xs text-txt-secondary truncate">{autoStatus.role}</p>
                        {/if}
                      </div>
                    </div>
                  {/each}
                  {#if card.agentNames.length > 1}
                    <p class="text-xs text-amber-400/70 font-mono mb-1">
                      👥 {card.agentNames.length}人
                    </p>
                  {/if}
                {:else}
                  <div class="flex items-center gap-2 mb-2 opacity-40">
                    <div class="w-8 h-8 rounded-lg border border-dashed border-white/20 flex items-center justify-center">
                      <span class="text-xs text-txt-secondary">?</span>
                    </div>
                    <div>
                      <p class="text-sm text-txt-secondary italic">待招聘</p>
                      <p class="text-xs text-txt-secondary/50 font-mono">{card.roleKey}</p>
                    </div>
                  </div>
                {/if}

                <!-- 任务信息（仅已分配人员显示）-->
                {#if !isUnassigned}
                  {@const smd = card.statusMd}
                  {@const isBusy = smd ? smd.work_status.includes("忙碌") : false}
                  {@const isIdle = smd ? smd.work_status.includes("空闲") : false}
                  {@const hasAgent = !!card.agentId}
                  {@const recentAct = card.agentId ? latestActivity[card.agentId] : null}
                  <div class="mt-3 pt-3 border-t border-white/5 space-y-1.5">
                    <!-- 最近动态（从 session 自动提取） -->
                    {#if recentAct}
                      <div class="flex items-start gap-1.5">
                        <span class="text-xs flex-shrink-0 mt-0.5">{recentAct.role === 'assistant' ? '💬' : '📨'}</span>
                        <p class="text-xs text-txt-primary/80 font-chinese line-clamp-2" title={recentAct.content}>
                          {recentAct.content}
                        </p>
                      </div>
                      <span class="text-xs text-txt-secondary/50 font-mono">{recentAct.relative_time}</span>
                    {:else if smd?.current_task && smd.current_task !== '无'}
                      <p class="text-xs text-txt-primary/80 font-chinese line-clamp-2" title={smd.current_task}>
                        {smd.current_task}
                      </p>
                    {:else}
                      <p class="text-xs text-txt-secondary font-chinese">{hasAgent ? '今日暂无活动' : '—'}</p>
                    {/if}
                  </div>
                {/if}

                <!-- 详情按钮 -->
                {#if card.agentId}
                  <div class="mt-3 pt-2 border-t border-white/5">
                    <button
                      on:click|stopPropagation={() => openTodayModal(card)}
                      class="w-full text-xs py-1.5 rounded bg-white/5 hover:bg-cyber-cyan/10 text-txt-secondary hover:text-cyber-cyan transition-colors"
                    >
                      📋 今日详情
                    </button>
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/each}
  {/if}
</div>

<!-- Today Modal -->
{#if showTodayModal && todayModalAgent}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4" on:click={closeTodayModal}>
    <div class="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>

    <div class="relative glass-card border border-cyber-cyan/20 w-full max-w-lg max-h-[80vh] flex flex-col" on:click|stopPropagation>
      <!-- Header -->
      <div class="flex items-center justify-between p-5 border-b border-white/10">
        <h2 class="font-rajdhani text-lg font-bold flex items-center gap-2">
          <span class="text-cyber-cyan">📝</span> 今日动态
          <span class="text-txt-secondary text-sm">— {todayModalAgent.agentNames.join("、")}</span>
        </h2>
        <button on:click={closeTodayModal} class="text-txt-secondary hover:text-txt-primary text-xl">✕</button>
      </div>

      <!-- Content -->
      <div class="p-5 overflow-y-auto flex-1">
        {#if todayLoading}
          <div class="text-center py-8">
            <div class="animate-spin w-6 h-6 border-2 border-cyber-cyan/30 border-t-cyber-cyan rounded-full mx-auto mb-3"></div>
            <p class="text-sm text-txt-secondary">加载中...</p>
          </div>
        {:else if todayActivities.length === 0}
          <div class="text-center py-8">
            <p class="text-3xl mb-3">📭</p>
            <p class="text-sm text-txt-secondary">今日暂无活动记录</p>
          </div>
        {:else}
          <div class="space-y-2">
            {#each todayActivities as activity}
              <div class="flex gap-3 py-2 border-b border-white/5 last:border-0">
                <div class="flex-shrink-0 mt-0.5">
                  {#if activity.role === 'assistant'}
                    <span class="text-cyber-cyan text-sm">💬</span>
                  {:else}
                    <span class="text-txt-secondary text-sm">📨</span>
                  {/if}
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-1">
                    <span class="text-xs font-mono text-cyber-cyan/70">{activity.relative_time || formatTime(activity.timestamp)}</span>
                    <span class="text-xs text-txt-secondary">{activity.role === 'assistant' ? '回复' : '收到'}</span>
                  </div>
                  <p class="text-sm text-txt-primary/90 line-clamp-3 font-chinese">{activity.content}</p>
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>

      <!-- Footer -->
      <div class="p-4 border-t border-white/10 flex justify-end">
        <button
          on:click={closeTodayModal}
          class="px-4 py-2 text-sm rounded bg-white/10 hover:bg-white/20 text-txt-primary transition-colors"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
{/if}
