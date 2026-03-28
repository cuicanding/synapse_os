<script lang="ts">
  import { tasks, missions, loading } from "../lib/stores";
  import MarkdownDetail from "../components/MarkdownDetail.svelte";

  // Filters
  let filterMission = "";
  let filterStatus = "";
  let filterAssignee = "";
  let filterDomain = "";
  let sortBy: "status" | "priority" | "time" = "time";

  // Expanded task detail
  let expandedTaskId: string | null = null;

  function toggleExpand(id: string) {
    expandedTaskId = expandedTaskId === id ? null : id;
  }

  // Unique values for filters
  $: uniqueMissions = [...new Set($tasks.map(t => t.mission_id).filter(Boolean))];
  $: uniqueAssignees = [...new Set($tasks.map(t => t.assignee).filter(a => a && a !== "待分配"))];
  $: uniqueDomains = [...new Set($tasks.map(t => t.domain).filter(Boolean))];

  const DOMAIN_LABELS: Record<string, string> = {
    infra: "基础设施域",
    infrastructure: "基础设施域",
    online: "在线业务域",
    offline: "离线业务域",
    growth: "增长域",
    marketing: "市场域",
    quant: "金蟾量化",
  };

  // Filtering
  $: filtered = $tasks.filter(t => {
    if (filterMission && t.mission_id !== filterMission) return false;
    if (filterStatus && t.status !== filterStatus) return false;
    if (filterAssignee && !t.assignee?.includes(filterAssignee)) return false;
    if (filterDomain && t.domain !== filterDomain) return false;
    return true;
  });

  // Sorting
  const statusOrder: Record<string, number> = {
    "in-progress": 0, assigned: 1, pending: 2, completed: 3, accepted: 4,
  };
  const priorityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };

  $: sorted = [...filtered].sort((a, b) => {
    if (sortBy === "status") {
      return (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9);
    } else if (sortBy === "priority") {
      return (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9);
    } else {
      const aTime = a.updated_at || a.created_at || "";
      const bTime = b.updated_at || b.created_at || "";
      return bTime.localeCompare(aTime);
    }
  });

  // Stats
  $: totalCount = $tasks.length;
  $: inProgressCount = $tasks.filter(t => t.status === "in-progress").length;
  $: pendingCount = $tasks.filter(t => t.status === "pending" || t.status === "assigned").length;
  $: completedCount = $tasks.filter(t => t.status === "completed" || t.status === "accepted").length;
  $: decisionCount = $tasks.filter(t => t.decision_status === "pending").length;

  // Helpers
  const statusLabel: Record<string, string> = {
    pending: "待分配", assigned: "已分配", "in-progress": "进行中",
    completed: "已完成", accepted: "已验收",
  };
  const statusClass: Record<string, string> = {
    pending: "status-pending", assigned: "status-in_progress",
    "in-progress": "status-in_progress", completed: "status-completed",
    accepted: "status-completed",
  };
  const priorityEmoji: Record<string, string> = { high: "🔴", medium: "🟡", low: "🟢" };
  const sourceLabel: Record<string, string> = { "real-business": "真实业务", "synapse-os": "SynapseOS 迭代" };

  function missionTitle(id: string): string {
    const m = $missions.find(m => m.id === id);
    return m?.title || id || "—";
  }
</script>

<div class="page-enter space-y-6">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <div>
      <h1 class="font-orbitron text-2xl font-bold neon-cyan flex items-center gap-2">
        <span>▤</span> 任务列表
      </h1>
      <p class="text-txt-secondary text-sm mt-1 font-chinese">
        所有使命下的任务总览 · {totalCount} 个任务
      </p>
    </div>
  </div>

  <!-- Stats -->
  <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
    <div class="glass-card p-4 space-y-1 text-center">
      <p class="font-orbitron text-2xl font-bold neon-cyan">{totalCount}</p>
      <p class="text-xs text-txt-secondary font-mono">总任务</p>
    </div>
    <div class="glass-card p-4 space-y-1 text-center">
      <p class="font-orbitron text-2xl font-bold neon-amber">{inProgressCount}</p>
      <p class="text-xs text-txt-secondary font-mono">进行中</p>
    </div>
    <div class="glass-card p-4 space-y-1 text-center">
      <p class="font-orbitron text-2xl font-bold text-txt-secondary">{pendingCount}</p>
      <p class="text-xs text-txt-secondary font-mono">待处理</p>
    </div>
    <div class="glass-card p-4 space-y-1 text-center">
      <p class="font-orbitron text-2xl font-bold neon-green">{completedCount}</p>
      <p class="text-xs text-txt-secondary font-mono">已完成</p>
    </div>
    <div class="glass-card p-4 space-y-1 text-center">
      <p class="font-orbitron text-2xl font-bold neon-violet">{decisionCount}</p>
      <p class="text-xs text-txt-secondary font-mono">待决策</p>
    </div>
  </div>

  <!-- Filters -->
  <div class="glass-card p-4 flex flex-wrap items-center gap-4">
    <div class="flex items-center gap-2">
      <span class="text-xs font-mono text-txt-secondary">使命:</span>
      <select bind:value={filterMission}
        class="bg-bg-light/40 border border-white/10 rounded px-2 py-1 text-xs font-mono text-txt-primary focus:border-cyber-cyan/40 focus:outline-none">
        <option value="">全部</option>
        {#each uniqueMissions as mid}
          <option value={mid}>{missionTitle(mid)}</option>
        {/each}
      </select>
    </div>
    <div class="flex items-center gap-2">
      <span class="text-xs font-mono text-txt-secondary">状态:</span>
      <select bind:value={filterStatus}
        class="bg-bg-light/40 border border-white/10 rounded px-2 py-1 text-xs font-mono text-txt-primary focus:border-cyber-cyan/40 focus:outline-none">
        <option value="">全部</option>
        <option value="in-progress">进行中</option>
        <option value="pending">待分配</option>
        <option value="assigned">已分配</option>
        <option value="completed">已完成</option>
        <option value="accepted">已验收</option>
      </select>
    </div>
    <div class="flex items-center gap-2">
      <span class="text-xs font-mono text-txt-secondary">负责人:</span>
      <select bind:value={filterAssignee}
        class="bg-bg-light/40 border border-white/10 rounded px-2 py-1 text-xs font-mono text-txt-primary focus:border-cyber-cyan/40 focus:outline-none">
        <option value="">全部</option>
        {#each uniqueAssignees as a}
          <option value={a}>{a}</option>
        {/each}
      </select>
    </div>
    <div class="flex items-center gap-2">
      <span class="text-xs font-mono text-txt-secondary">领域:</span>
      <select bind:value={filterDomain}
        class="bg-bg-light/40 border border-white/10 rounded px-2 py-1 text-xs font-mono text-txt-primary focus:border-cyber-cyan/40 focus:outline-none">
        <option value="">全部</option>
        {#each uniqueDomains as d}
          <option value={d}>{DOMAIN_LABELS[d] || d}</option>
        {/each}
      </select>
    </div>

    <div class="flex-1"></div>

    <div class="flex items-center gap-2">
      <span class="text-xs font-mono text-txt-secondary">排序:</span>
      <button on:click={() => sortBy = "status"}
        class="px-2 py-1 rounded text-xs font-mono {sortBy === 'status' ? 'bg-cyber-cyan/20 text-cyber-cyan border border-cyber-cyan/30' : 'bg-bg-light/30 text-txt-secondary border border-white/10'} transition-colors">
        状态
      </button>
      <button on:click={() => sortBy = "priority"}
        class="px-2 py-1 rounded text-xs font-mono {sortBy === 'priority' ? 'bg-cyber-cyan/20 text-cyber-cyan border border-cyber-cyan/30' : 'bg-bg-light/30 text-txt-secondary border border-white/10'} transition-colors">
        优先级
      </button>
      <button on:click={() => sortBy = "time"}
        class="px-2 py-1 rounded text-xs font-mono {sortBy === 'time' ? 'bg-cyber-cyan/20 text-cyber-cyan border border-cyber-cyan/30' : 'bg-bg-light/30 text-txt-secondary border border-white/10'} transition-colors">
        时间
      </button>
    </div>

    <span class="text-xs font-mono text-txt-secondary">{sorted.length} 条结果</span>
  </div>

  <!-- Task List -->
  {#if $loading}
    <div class="space-y-3">
      {#each Array(4) as _}
        <div class="glass-card p-6 h-24 animate-pulse bg-bg-mid/30"></div>
      {/each}
    </div>
  {:else if sorted.length === 0}
    <div class="glass-card glow-border p-16 text-center space-y-4">
      <div class="text-5xl">📭</div>
      <h2 class="font-rajdhani text-xl font-semibold text-txt-secondary">无匹配任务</h2>
      <p class="text-txt-secondary font-chinese">试试调整筛选条件</p>
    </div>
  {:else}
    <div class="space-y-3">
      {#each sorted as task (task.id)}
        {@const isExpanded = expandedTaskId === task.id}
        <div class="glass-card transition-all {isExpanded ? 'border-cyber-cyan/30' : 'hover:border-white/10'}">
          <!-- Task card header (clickable) -->
          <button class="w-full p-4 text-left" on:click={() => toggleExpand(task.id)}>
            <div class="flex items-start justify-between gap-3">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap mb-1">
                  <span class="font-mono text-xs text-cyber-cyan/60">{task.id}</span>
                  <span class="text-xs">{priorityEmoji[task.priority] || "⚪"}</span>
                  <span class="status-badge {statusClass[task.status] || 'status-pending'} text-xs">
                    {statusLabel[task.status] || task.status}
                  </span>
                  {#if task.decision_status === "pending"}
                    <span class="status-badge status-blocked text-xs">待果爸决策</span>
                  {:else if task.decision_status === "decided"}
                    <span class="status-badge status-completed text-xs">已决策</span>
                  {/if}
                  {#if task.source_type}
                    <span class="px-1.5 py-0.5 rounded text-xs bg-cyber-violet/10 border border-cyber-violet/20 text-cyber-violet/80">
                      {sourceLabel[task.source_type] || task.source_type}
                    </span>
                  {/if}
                </div>
                <h3 class="font-rajdhani text-base font-semibold leading-tight">{task.title}</h3>
                <div class="flex items-center gap-3 mt-2 text-xs font-mono text-txt-secondary">
                  <span>👤 {task.assignee || "待分配"}</span>
                  {#if task.domain}
                    <span class="px-1.5 py-0.5 rounded bg-cyber-cyan/10 border border-cyber-cyan/20 text-cyber-cyan/80">{DOMAIN_LABELS[task.domain] || task.domain}</span>
                  {/if}
                  {#if task.mission_id}
                    <span>◎ <a href="#/mission/{encodeURIComponent(task.mission_id)}" class="text-cyber-cyan/60 hover:text-cyber-cyan" on:click|stopPropagation>{missionTitle(task.mission_id)}</a></span>
                  {/if}
                  <span>📅 {task.created_at || "—"}</span>
                </div>
              </div>
              <span class="text-txt-secondary text-sm transition-transform flex-shrink-0 {isExpanded ? 'rotate-90' : ''}">▶</span>
            </div>
          </button>

          <!-- Expanded detail -->
          {#if isExpanded}
            <div class="px-4 pb-4 pt-0 border-t border-white/5 space-y-3">
              {#if task.content}
                <MarkdownDetail title="📋 任务描述" content={task.content} accentColor="cyan" />
              {/if}
              {#if task.proposal_content}
                <MarkdownDetail title="💡 提案内容" content={task.proposal_content} accentColor="amber" />
              {/if}
              {#if task.decision_detail}
                <MarkdownDetail
                  title="{task.decision_status === 'pending' ? '⏳ 待决策' : '✅ 已决策'}"
                  content={task.decision_detail}
                  accentColor={task.decision_status === 'pending' ? 'amber' : 'green'}
                />
              {/if}
              <div class="flex items-center gap-4 text-xs font-mono text-txt-secondary">
                {#if task.creator}
                  <span>创建者: <span class="text-cyber-violet">{task.creator}</span></span>
                {/if}
                {#if task.mission_title}
                  <span>使命: <span class="text-cyber-cyan">{task.mission_title}</span></span>
                {/if}
              </div>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>
