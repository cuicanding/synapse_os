<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { statusPanel, statusWsConnected, startStatusWs, stopStatusWs } from "../lib/status-ws";
  import { fetchStatusPanel, type AgentStatus, type StatusPanel } from "../lib/api";
  import { showDifficultyModal, showHistorySidebar, statusDetailAgent } from "../lib/stores";
  import DifficultyModal from "./DifficultyModal.svelte";
  import StatusHistory from "./StatusHistory.svelte";

  let loading = true;
  let refreshTimer: ReturnType<typeof setInterval> | null = null;
  let registry: Record<string, any> = {};
  let collapsed: Record<string, boolean> = {};

  // ─── Domain 定义 ─────────────────────────────────────────────────────────
  const DOMAIN_META: Record<string, { name: string; emoji: string; color: string; desc: string }> = {
    infrastructure: { name: "基础设施域", emoji: "🔧", color: "#00E5FF", desc: "SynapseOS 等 AI-Native 管理工具" },
    online:         { name: "在线业务域", emoji: "🌐", color: "#22c55e", desc: "线上业务系统建设" },
    offline:        { name: "离线业务域", emoji: "🗄️", color: "#a78bfa", desc: "线下/批处理业务系统" },
    growth:         { name: "增长域",     emoji: "📈", color: "#f59e0b", desc: "用户增长与数据分析" },
    marketing:       { name: "市场域",     emoji: "📣", color: "#f472b6", desc: "市场推广与投放" },
    quant:           { name: "金蟾量化团队", emoji: "🦎", color: "#f59e0b", desc: "量化策略研究、开发与数据基建" },
  };

  const ROLE_SLOTS: Record<string, { roleKey: string; roleLabel: string; domain: string }[]> = {
    infrastructure: [
      { roleKey: "infrastructure-architect",        roleLabel: "架构师",   domain: "infrastructure" },
      { roleKey: "infrastructure-product-designer", roleLabel: "产品设计", domain: "infrastructure" },
      { roleKey: "infrastructure-developer",        roleLabel: "开发者",   domain: "infrastructure" },
    ],
    online: [
      { roleKey: "online-architect",   roleLabel: "架构师", domain: "online" },
      { roleKey: "online-developer",  roleLabel: "开发者", domain: "online" },
    ],
    offline: [
      { roleKey: "offline-architect",  roleLabel: "架构师", domain: "offline" },
      { roleKey: "offline-developer",  roleLabel: "开发者", domain: "offline" },
    ],
    growth: [
      { roleKey: "growth-architect",  roleLabel: "架构师", domain: "growth" },
      { roleKey: "growth-developer",  roleLabel: "开发者", domain: "growth" },
    ],
    marketing: [
      { roleKey: "marketing-architect",  roleLabel: "架构师", domain: "marketing" },
      { roleKey: "marketing-developer",  roleLabel: "开发者", domain: "marketing" },
    ],
    quant: [
      { roleKey: "quant-analyst",       roleLabel: "策略分析师",     domain: "quant" },
      { roleKey: "quant-developer",     roleLabel: "策略开发师",     domain: "quant" },
      { roleKey: "quant-data-engineer", roleLabel: "策略数据工程师", domain: "quant" },
    ],
  };

  // ─── 从 registry 拉取完整角色表 ─────────────────────────────────────────
  async function loadRegistry() {
    try {
      const r = await fetch("/api/registry");
      if (r.ok) {
        registry = await r.json();
      }
    } catch (e) {
      console.warn("[team] registry load failed, using empty:", e);
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

  $: allCards = ((): RoleSlotCard[] => {
    const cards: RoleSlotCard[] = [];
    for (const [domain, slots] of Object.entries(ROLE_SLOTS)) {
      for (const slot of slots) {
        const reg = registry[slot.roleKey] || {};
        const agentId = reg.agentId || null;
        const assignedTo = reg.assigned_to || null;

        // 匹配策略：agentId 精确匹配 > 名字包含匹配
        let reported: AgentStatus | null = null;
        if (agentId && reportedMap[agentId]) {
          reported = reportedMap[agentId];
        } else if (assignedTo) {
          // 遍历 status panel，找一个 agent_name 能匹配 assignedTo 的
          const agents = $statusPanel?.agents || [];
          for (const a of agents) {
            if (a.agent_name && nameMatches(assignedTo, a.agent_name)) {
              reported = a;
              break;
            }
          }
        }
        if (assignedTo) {
          console.log(`[team] match ${slot.roleKey}: assigned="${assignedTo}" → reported=${reported?.agent_name || 'NONE'} (agentId=${agentId})`);
        }

        let onlineStatus: RoleSlotCard["onlineStatus"] = "unassigned";
        if (reported) {
          onlineStatus = reported.is_stale ? "stale" : "online";
        } else if (agentId || assignedTo) {
          // 有分配但没有上报记录
          onlineStatus = "stale";
        }

        cards.push({
          roleKey: slot.roleKey,
          roleLabel: slot.roleLabel,
          domain,
          agentName: reg.assigned_to || null,
          agentNames: normalizeNames(reg.assigned_to),
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
        });
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

  onMount(() => {
    startStatusWs();
    loadRegistry();
    refresh();
    refreshTimer = setInterval(() => { refresh(); loadRegistry(); }, 30000);
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
              <span class="text-cyber-amber font-bold">{staleSlots}</span> 未报到
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
            {#each cards as card (card.roleKey)}
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
                    <span class="w-2 h-2 rounded-full bg-cyber-amber" title="未报到"></span>
                  {:else}
                    <span class="w-2 h-2 rounded-full bg-white/10" title="未分配"></span>
                  {/if}
                </div>

                <!-- 角色标签 -->
                <div class="text-xs font-mono text-txt-secondary mb-2">{card.roleLabel}</div>

                <!-- 人员信息 -->
                {#if card.agentNames.length > 0}
                  {#each card.agentNames as name, ni}
                    <div class="flex items-center gap-2 {ni > 0 ? 'mt-1.5 pt-1.5 border-t border-white/5' : 'mb-2'}">
                      <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500/60 to-amber-700/60 flex items-center justify-center">
                        <span class="font-orbitron text-xs font-bold text-txt-primary">
                          {initials(name)}
                        </span>
                      </div>
                      <div class="flex-1 min-w-0">
                        <p class="text-sm font-semibold text-txt-primary truncate">{name}</p>
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
                  <div class="mt-3 pt-3 border-t border-white/5 space-y-1.5">
                    <!-- 当前任务 -->
                    <div>
                      <p class="text-xs text-txt-secondary font-mono">任务</p>
                      <p class="text-xs text-txt-primary font-chinese truncate" title={card.currentTask}>
                        {card.currentTask || "—"}
                      </p>
                    </div>

                    <!-- 进展 -->
                    <div class="flex items-center justify-between">
                      <span class="text-xs text-txt-secondary font-mono">进展</span>
                      <span class="text-xs">{progressLabel(card.progress)}</span>
                    </div>

                    <!-- 困难 / 待决策 -->
                    <div class="flex gap-2">
                      {#if hasBlocking}
                        <span class="text-xs bg-cyber-red/10 border border-cyber-red/20 text-cyber-red rounded px-1.5 py-0.5">
                          🚨 {card.difficulty?.slice(0, 20) || '阻塞中'}
                        </span>
                      {/if}
                      {#if hasDecision}
                        <span class="text-xs bg-cyber-amber/10 border border-cyber-amber/20 text-cyber-amber rounded px-1.5 py-0.5">
                          🔔 {card.needsDecision?.slice(0, 20) || '待决策'}
                        </span>
                      {/if}
                    </div>

                    <!-- 最后报到时间 -->
                    <p class="text-xs text-txt-secondary/60 font-mono pt-1">
                      📡 {timeAgo(card.lastReportAt)}
                    </p>
                  </div>
                {/if}

                <!-- 阻塞/决策详情 -->
                {#if hasBlocking && card.difficulty}
                  <div class="mt-2 p-2 rounded bg-cyber-red/10 border border-cyber-red/20">
                    <p class="text-xs text-cyber-red/90 font-chinese">{card.difficulty}</p>
                  </div>
                {/if}
                {#if hasDecision && card.needsDecision}
                  <div class="mt-2 p-2 rounded bg-cyber-amber/10 border border-cyber-amber/20">
                    <p class="text-xs text-cyber-amber/90 font-chinese">{card.needsDecision}</p>
                  </div>
                {/if}

                <!-- 操作按钮 -->
                {#if card.agentId}
                  <div class="mt-3 pt-2 border-t border-white/5 flex gap-2">
                    <button
                      onclick={() => openHistory(card.agentId || '')}
                      class="flex-1 text-xs py-1 rounded bg-white/5 hover:bg-white/10 text-txt-secondary hover:text-txt-primary transition-colors"
                    >
                      📋 历史
                    </button>
                    <button
                      onclick={() => openDifficulty(card.agentId || '')}
                      class="flex-1 text-xs py-1 rounded bg-white/5 hover:bg-cyber-red/10 text-txt-secondary hover:text-cyber-red transition-colors"
                    >
                      🚨 困难
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
