<script lang="ts">
  import { missions, tasks, loading } from "../lib/stores";
  import MarkdownDetail from "../components/MarkdownDetail.svelte";

  // Detect if we're on a detail route: #/mission/:id
  let detailId: string | null = null;

  function parseHash() {
    const h = location.hash || "";
    const m = h.match(/^#\/mission\/(.+)$/);
    detailId = m ? decodeURIComponent(m[1]) : null;
  }

  parseHash();
  // Re-parse on hash change (Svelte doesn't auto-track location.hash)
  function onHashChange() { parseHash(); }
  if (typeof window !== "undefined") {
    window.addEventListener("hashchange", onHashChange);
  }

  // Current detail mission
  $: detailMission = detailId ? $missions.find(m => m.id === detailId) || null : null;

  // Tasks for the detail mission (with domain filter), sorted by updated_at desc
  $: detailTasks = detailMission
    ? [...$tasks.filter(t => t.mission_id === detailMission!.id)].sort((a, b) => {
        const aTime = a.updated_at || a.created_at || "";
        const bTime = b.updated_at || b.created_at || "";
        return bTime.localeCompare(aTime);
      })
    : [];

  // Stats for detail view
  $: detailTotal = detailTasks.length;
  $: detailCounts = {
    in_progress: detailTasks.filter(t => t.status === "in-progress").length,
    pending: detailTasks.filter(t => t.status === "pending").length,
    assigned: detailTasks.filter(t => t.status === "assigned").length,
    completed: detailTasks.filter(t => t.status === "completed").length,
    accepted: detailTasks.filter(t => t.status === "accepted").length,
    pending_approval: detailTasks.filter(t => t.status === "pending-approval").length,
    pending_acceptance: detailTasks.filter(t => t.status === "pending-acceptance").length,
    rejected: detailTasks.filter(t => t.status === "rejected").length,
  };
  $: detailProgress = detailTotal > 0
    ? Math.round(((detailCounts.completed + detailCounts.accepted) / detailTotal) * 100)
    : 0;

  // Mission list stats (tasks per mission)
  function missionTaskCount(missionId: string): number {
    return $tasks.filter(t => t.mission_id === missionId).length;
  }
  function missionProgress(missionId: string): number {
    const mt = $tasks.filter(t => t.mission_id === missionId);
    if (mt.length === 0) return 0;
    const done = mt.filter(t => t.status === "completed" || t.status === "accepted").length;
    return Math.round((done / mt.length) * 100);
  }

  const statusLabel: Record<string, string> = {
    pending: "待分配", assigned: "已分配", "in-progress": "进行中",
    completed: "已完成", accepted: "已验收", "pending-approval": "待审批",
    "pending-acceptance": "待验收", rejected: "已驳回",
  };
  const statusClass: Record<string, string> = {
    pending: "status-pending", assigned: "status-in_progress",
    "in-progress": "status-in_progress", completed: "status-completed",
    accepted: "status-completed", "pending-approval": "status-pending_approval",
    "pending-acceptance": "status-pending_acceptance", rejected: "status-rejected",
  };
  const priorityEmoji: Record<string, string> = {
    high: "🔴", medium: "🟡", low: "🟢",
  };

  // Domain filter (removed per 董事长 request)
</script>

{#if detailId && detailMission}
  <!-- ═══════════ DETAIL VIEW ═══════════ -->
  <div class="page-enter space-y-8">
    <!-- Back button -->
    <a href="#/" class="inline-flex items-center gap-2 text-sm text-txt-secondary hover:text-cyber-cyan transition-colors font-mono">
      ← 返回使命列表
    </a>

    <!-- Hero Card -->
    <div class="glass-card glow-border p-8">
      <div class="flex items-start justify-between flex-wrap gap-6">
        <div class="space-y-3 flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="status-badge status-in_progress">
              <span class="w-1.5 h-1.5 rounded-full bg-cyber-amber pulse-glow"></span>
              {detailMission.status === "active" ? "进行中" : (detailMission.status || "—")}
            </span>
            <span class="font-mono text-xs text-txt-secondary">ID: {detailMission.id}</span>
          </div>
          <h1 class="font-orbitron text-3xl font-bold neon-cyan">
            {detailMission.title}
          </h1>
          <p class="text-txt-secondary max-w-2xl leading-relaxed font-chinese text-sm">
            {detailMission.description || "—"}
          </p>
          <p class="text-xs font-mono text-txt-secondary mt-1">
            创建于 {detailMission.created_at || "—"}
          </p>

          {#if detailMission.goals?.length}
            <div class="mt-4 flex flex-wrap gap-2">
              {#each detailMission.goals as goal, i}
                <span class="px-3 py-1 rounded-full text-xs font-chinese bg-bg-light/60 border border-cyber-cyan/20 text-txt-secondary">
                  {#if i === 0}🎯{:else if i === 1}📐{:else if i === 2}🔄{:else}📌{/if}
                  {goal.title}
                </span>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Progress Ring -->
        <div class="flex flex-col items-center gap-2">
          <div class="relative w-32 h-32">
            <svg class="w-full h-full -rotate-90" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="42" fill="none" stroke="#1E293B" stroke-width="8"/>
              <circle cx="50" cy="50" r="42" fill="none"
                stroke="url(#progressGradD)" stroke-width="8" stroke-linecap="round"
                stroke-dasharray="{2 * Math.PI * 42}"
                stroke-dashoffset="{2 * Math.PI * 42 * (1 - detailProgress / 100)}"
                style="transition: stroke-dashoffset 0.6s ease"/>
              <defs>
                <linearGradient id="progressGradD" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stop-color="#00E5FF"/>
                  <stop offset="100%" stop-color="#7C3AED"/>
                </linearGradient>
              </defs>
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center">
              <span class="font-orbitron text-2xl font-bold neon-cyan">{detailProgress}%</span>
              <span class="text-xs text-txt-secondary">完成度</span>
            </div>
          </div>
          <span class="text-xs font-mono text-txt-secondary">{detailCounts.completed + detailCounts.accepted}/{detailTotal} 任务</span>
        </div>
      </div>
    </div>

    <!-- Stats Row -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
      <div class="glass-card p-5 space-y-1">
        <p class="text-xs text-txt-secondary font-mono uppercase tracking-wider">总任务</p>
        <p class="font-orbitron text-2xl font-bold neon-cyan">{detailTotal}</p>
      </div>
      <div class="glass-card p-5 space-y-1">
        <p class="text-xs text-txt-secondary font-mono uppercase tracking-wider">进行中</p>
        <p class="font-orbitron text-2xl font-bold neon-amber">{detailCounts.in_progress}</p>
      </div>
      <div class="glass-card p-5 space-y-1">
        <p class="text-xs text-txt-secondary font-mono uppercase tracking-wider">待分配</p>
        <p class="font-orbitron text-2xl font-bold text-txt-secondary">{detailCounts.pending + detailCounts.assigned}</p>
      </div>
      <div class="glass-card p-5 space-y-1">
        <p class="text-xs text-txt-secondary font-mono uppercase tracking-wider">已验收</p>
        <p class="font-orbitron text-2xl font-bold neon-green">{detailCounts.accepted}</p>
      </div>
      <div class="glass-card p-5 space-y-1">
        <p class="text-xs text-txt-secondary font-mono uppercase tracking-wider">待审批</p>
        <p class="font-orbitron text-2xl font-bold neon-amber">{detailCounts.pending_approval}</p>
      </div>
      <div class="glass-card p-5 space-y-1">
        <p class="text-xs text-txt-secondary font-mono uppercase tracking-wider">待验收</p>
        <p class="font-orbitron text-2xl font-bold text-cyber-violet">{detailCounts.pending_acceptance}</p>
      </div>
    </div>

    <!-- Team -->
    {#if detailMission.team_overview?.length}
      <div class="glass-card p-6">
        <h2 class="font-rajdhani text-xl font-semibold mb-4 flex items-center gap-2">
          <span class="neon-violet">▸</span> 承担团队
        </h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
          {#each detailMission.team_overview as member, i}
            <div class="flex items-center gap-3 p-3 rounded-lg bg-bg-light/20">
              <div class="w-10 h-10 rounded-lg bg-gradient-to-br {i % 2 === 0 ? 'from-cyber-cyan to-cyber-violet' : 'from-cyber-violet to-cyber-green'} p-0.5">
                <div class="w-full h-full rounded-[6px] bg-bg-mid flex items-center justify-center">
                  <span class="text-sm font-bold text-txt-primary">{member.member?.[0] || "?"}</span>
                </div>
              </div>
              <div>
                <p class="font-rajdhani font-semibold text-sm">{member.member}</p>
                <p class="text-xs text-txt-secondary">{member.role}</p>
                <p class="text-xs text-cyber-cyan/60 mt-0.5">{member.duty}</p>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Milestones -->
    {#if detailMission.milestones?.length}
      <div class="glass-card p-6">
        <h2 class="font-rajdhani text-xl font-semibold mb-5 flex items-center gap-2">
          <span class="neon-cyan">▸</span> 里程碑
        </h2>
        <div class="space-y-3">
          {#each detailMission.milestones as ms, i}
            <div class="flex items-center gap-4 p-3 rounded-lg bg-bg-light/20">
              <div class="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center
                {ms.status === 'completed' ? 'bg-cyber-green/20 border border-cyber-green/40'
                  : ms.status === 'in-progress' ? 'bg-cyber-amber/20 border border-cyber-amber/40'
                  : 'bg-bg-light border border-cyber-cyan/20'}">
                {#if ms.status === "completed"}
                  <span class="text-cyber-green font-bold text-sm">✓</span>
                {:else if ms.status === "in-progress"}
                  <span class="w-2 h-2 rounded-full bg-cyber-amber pulse-glow"></span>
                {:else}
                  <span class="text-txt-secondary font-mono text-xs">{i + 1}</span>
                {/if}
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium">{ms.title}</p>
              </div>
              <span class="status-badge {ms.status === 'completed' ? 'status-completed' : ms.status === 'in-progress' ? 'status-in_progress' : 'status-pending'}">
                {ms.status === "completed" ? "已完成" : ms.status === "in-progress" ? "进行中" : "待启动"}
              </span>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Tasks under this mission -->
    <div class="glass-card p-6">
      <h2 class="font-rajdhani text-xl font-semibold mb-5 flex items-center gap-2">
        <span class="neon-violet">▸</span> 使命下的任务
        <span class="text-xs font-mono text-txt-secondary ml-2">({detailTotal} 个)</span>
      </h2>
      <div class="space-y-3">
        {#each detailTasks as task}
          <div class="p-4 rounded-lg bg-bg-light/20 hover:bg-bg-light/40 transition-colors border border-transparent hover:border-cyber-cyan/20">
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
                  {/if}
                </div>
                <h3 class="font-rajdhani text-base font-semibold leading-tight">{task.title}</h3>
                <div class="flex items-center gap-3 mt-2 text-xs font-mono text-txt-secondary">
                  <span>👤 {task.assignee || "待分配"}</span>
                  <span>📅 {task.created_at}</span>
                  {#if task.iteration_round}
                    <span class="text-amber-400">🔄 迭代第{task.iteration_round}轮</span>
                  {/if}
                  {#if task.iteration_driver}
                    <span class="text-amber-400/60">由 {task.iteration_driver} 驱动</span>
                  {/if}
                </div>
                {#if task.proposal_content}
                  <div class="mt-2">
                    <MarkdownDetail title="💡 提案内容" content={task.proposal_content} accentColor="amber" />
                  </div>
                {/if}
              </div>
            </div>
          </div>
        {/each}
        {#if detailTasks.length === 0}
          <p class="text-txt-secondary text-sm font-chinese text-center py-4">暂无关联任务</p>
        {/if}
      </div>
    </div>
  </div>

{:else}
  <!-- ═══════════ LIST VIEW ═══════════ -->
  <div class="page-enter space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="font-orbitron text-2xl font-bold neon-cyan flex items-center gap-2">
          <span>◎</span> 使命总览
        </h1>
        <p class="text-txt-secondary text-sm mt-1 font-chinese">
          长期持续迭代的战略目标 · {$missions.length} 个使命
        </p>
      </div>
    </div>

    {#if $loading}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
        {#each Array(2) as _}
          <div class="glass-card p-6 h-48 animate-pulse bg-bg-mid/30"></div>
        {/each}
      </div>
    {:else if $missions.length === 0}
      <div class="glass-card glow-border p-16 text-center space-y-4">
        <div class="text-5xl">📭</div>
        <h2 class="font-rajdhani text-xl font-semibold text-txt-secondary">暂无使命</h2>
        <p class="text-txt-secondary font-chinese">在 missions/ 目录下创建使命文件</p>
      </div>
    {:else}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
        {#each $missions as m (m.id)}
          {@const tc = missionTaskCount(m.id)}
          {@const prog = missionProgress(m.id)}
          <a href="#/mission/{encodeURIComponent(m.id)}"
            class="glass-card p-6 hover:border-cyber-cyan/30 transition-all hover:scale-[1.01] block">
            <div class="flex items-start justify-between gap-4">
              <div class="flex-1 min-w-0 space-y-2">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="status-badge {m.status === 'active' ? 'status-in_progress' : 'status-completed'}">
                    <span class="w-1.5 h-1.5 rounded-full {m.status === 'active' ? 'bg-cyber-amber pulse-glow' : 'bg-cyber-green'}"></span>
                    {m.status === "active" ? "进行中" : (m.status || "—")}
                  </span>
                  <span class="font-mono text-xs text-txt-secondary">{m.id}</span>
                </div>
                <h2 class="font-rajdhani text-xl font-bold text-txt-primary">{m.title}</h2>
                <p class="text-txt-secondary text-sm font-chinese line-clamp-2">{m.description || "—"}</p>

                {#if m.goals?.length}
                  <div class="flex flex-wrap gap-1.5 mt-1">
                    {#each m.goals.slice(0, 3) as goal}
                      <span class="px-2 py-0.5 rounded text-xs bg-bg-light/40 border border-cyber-cyan/10 text-txt-secondary">
                        {goal.title}
                      </span>
                    {/each}
                    {#if m.goals.length > 3}
                      <span class="text-xs text-txt-secondary">+{m.goals.length - 3}</span>
                    {/if}
                  </div>
                {/if}

                {#if m.driver}
                  <div class="flex items-center gap-1.5 mt-2">
                    <span class="px-2 py-0.5 rounded text-xs bg-amber-500/10 border border-amber-500/20 text-amber-400">
                      👑 一号位: {m.driver}
                    </span>
                    {#if m.workflow_interval}
                      <span class="px-2 py-0.5 rounded text-xs bg-bg-light/40 border border-white/5 text-txt-secondary">
                        🔄 {m.workflow_interval}
                      </span>
                    {/if}
                  </div>
                {/if}

                <div class="flex items-center gap-4 text-xs font-mono text-txt-secondary pt-1">
                  <span>📋 {tc} 个任务</span>
                  <span>📅 {m.created_at || "—"}</span>
                </div>
              </div>

              <!-- Mini progress ring -->
              <div class="flex-shrink-0">
                <div class="relative w-16 h-16">
                  <svg class="w-full h-full -rotate-90" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="42" fill="none" stroke="#1E293B" stroke-width="10"/>
                    <circle cx="50" cy="50" r="42" fill="none"
                      stroke="url(#progGrad{m.id})" stroke-width="10" stroke-linecap="round"
                      stroke-dasharray="{2 * Math.PI * 42}"
                      stroke-dashoffset="{2 * Math.PI * 42 * (1 - prog / 100)}"
                      style="transition: stroke-dashoffset 0.6s ease"/>
                    <defs>
                      <linearGradient id="progGrad{m.id}" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stop-color="#00E5FF"/>
                        <stop offset="100%" stop-color="#7C3AED"/>
                      </linearGradient>
                    </defs>
                  </svg>
                  <div class="absolute inset-0 flex items-center justify-center">
                    <span class="font-orbitron text-xs font-bold neon-cyan">{prog}%</span>
                  </div>
                </div>
              </div>
            </div>
          </a>
        {/each}
      </div>
    {/if}
  </div>
{/if}
