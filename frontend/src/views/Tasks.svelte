<script lang="ts">
  import { tasks, missions, loading, communicateRequest } from "../lib/stores";
  import MarkdownDetail from "../components/MarkdownDetail.svelte";
  import { marked } from "marked";
  import DOMPurify from "dompurify";
  import PhaseCard from "../components/PhaseCard.svelte";
  import DiscussionPanel from "../components/DiscussionPanel.svelte";
  import {
    fetchTaskPhases,
    fetchFileContent,
    approveTask,
    rejectTask,
    acceptTask,
    completeTask,
    abandonTask,
    type PhaseInfo,
  } from "../lib/api";

  // Filters
  let filterMission = "";
  let filterStatus = "";
  let filterAssignee = "";
  let filterDomain = "";
  let sortBy: "status" | "priority" | "time" = "time";

  // Expanded task detail
  let expandedTaskId: string | null = null;

  // Viewed tasks tracking (localStorage)
  let viewedTasks: Set<string> = new Set();
  let viewedTasksVersion = 0;  // trigger reactivity

  function loadViewedTasks() {
    try {
      const stored = localStorage.getItem("viewedTasks");
      if (stored) {
        viewedTasks = new Set(JSON.parse(stored));
        viewedTasksVersion++;
      }
    } catch (e) {
      console.warn("Failed to load viewedTasks:", e);
    }
  }
  function saveViewedTasks() {
    try {
      localStorage.setItem("viewedTasks", JSON.stringify([...viewedTasks]));
    } catch (e) {
      console.warn("Failed to save viewedTasks:", e);
    }
  }
  function markTaskViewed(taskId: string) {
    if (!viewedTasks.has(taskId)) {
      viewedTasks.add(taskId);
      saveViewedTasks();
      viewedTasksVersion++;
    }
  }

  function isViewed(taskId: string): boolean {
    // Reference viewedTasksVersion to trigger dependency tracking
    viewedTasksVersion;
    return viewedTasks.has(taskId);
  }

  // Phase info for expanded task
  let phaseInfo: PhaseInfo[] = [];
  let phaseLoading = false;

  // Markdown rendering
  marked.setOptions({ breaks: true, gfm: true });
  function renderMd(text: string): string {
    return DOMPurify.sanitize(marked.parse(text) as string);
  }

  // Artifact preview
  let previewArtifact: { name: string; path: string } | null = null;
  let previewContent = "";
  let previewError = "";
  let previewLoading = false;

  async function openArtifactPreview(artifact: { name: string; path: string }) {
    if (!artifact.path.endsWith(".md")) return;
    previewArtifact = artifact;
    previewContent = "";
    previewError = "";
    previewLoading = true;
    try {
      const res = await fetchFileContent(artifact.path);
      if (res.error) {
        previewError = res.error;
      } else {
        previewContent = res.content;
      }
    } catch (e: any) {
      previewError = e.message || "Failed to load";
    } finally {
      previewLoading = false;
    }
  }

  function closePreview() {
    previewArtifact = null;
    previewContent = "";
    previewError = "";
  }

  // Parse artifacts from task content
  interface Artifact {
    name: string;
    type: string;
    path: string;
    time?: string;
  }

  function parseArtifacts(content: string): Artifact[] {
    if (!content) return [];
    const artifacts: Artifact[] = [];

    // Only scan within the ## 产出物 section to avoid matching paths in descriptions
    let artifactContent = "";
    const sectionMatch = content.match(/## 产出物\s*\n([\s\S]*?)(?=\n## |\n---\n|$)/);
    if (sectionMatch) {
      artifactContent = sectionMatch[1];
    } else {
      return [];
    }

    // Pattern 1: - **name** (TYPE): `path.md` — time
    const p1 = /-\s*\*\*([^*]+)\*\*\s*\((\w+)\):\s*`([^`]+\.md)`\s*(?:—|-)\s*([^\n]+)/g;
    let m;
    while ((m = p1.exec(artifactContent)) !== null) {
      artifacts.push({ name: m[1].trim(), type: m[2], path: m[3], time: m[4].trim() });
    }

    // Pattern 2: - **name**: `path.md`
    const p2 = /-\s*\*\*([^*]+)\*\*:\s*`([^`]+\.md)`/g;
    while ((m = p2.exec(artifactContent)) !== null) {
      if (!artifacts.some(a => a.path === m[2])) {
        artifacts.push({ name: m[1].trim(), type: "DOC", path: m[2] });
      }
    }

    // Pattern 3: Table row: | 产出 | `path.md` | 说明 |
    const p3 = /\|\s*产出\s*\|\s*`([^`]+\.md)`/g;
    while ((m = p3.exec(artifactContent)) !== null) {
      if (!artifacts.some(a => a.path === m[1])) {
        artifacts.push({ name: m[1].split("/").pop() || m[1], type: "DOC", path: m[1] });
      }
    }

    // Pattern 4: List item with .md path
    const p4 = /[-*]\s*[^\n`]*`([^`]+\.md)`/g;
    while ((m = p4.exec(artifactContent)) !== null) {
      if (!artifacts.some(a => a.path === m[1])) {
        artifacts.push({ name: m[1].split("/").pop() || m[1], type: "DOC", path: m[1] });
      }
    }

    // Pattern 5: Fallback — backtick-quoted .md path within 产出物 section
    const p5 = /`([^`]+\.md)`/g;
    while ((m = p5.exec(artifactContent)) !== null) {
      if (!artifacts.some(a => a.path === m[1])) {
        artifacts.push({ name: m[1].split("/").pop() || m[1], type: "DOC", path: m[1] });
      }
    }

    return artifacts;
  }

  async function toggleExpand(id: string) {
    if (expandedTaskId === id) {
      expandedTaskId = null;
      phaseInfo = [];
    } else {
      expandedTaskId = id;
      markTaskViewed(id);
      // Fetch phase info
      phaseLoading = true;
      try {
        phaseInfo = await fetchTaskPhases(id);
      } catch (e) {
        console.error("Failed to fetch phases:", e);
        phaseInfo = [];
      } finally {
        phaseLoading = false;
      }
    }
  }

  // Action handlers
  async function handleApprove(taskId: string) {
    try {
      await approveTask(taskId);
    } catch (e) {
      console.error("Approve failed:", e);
    }
  }

  async function handleReject(taskId: string) {
    const reason = prompt("驳回原因：");
    if (reason !== null) {
      try {
        await rejectTask(taskId);
      } catch (e) {
        console.error("Reject failed:", e);
      }
    }
  }

  async function handleAccept(taskId: string) {
    try {
      await acceptTask(taskId);
    } catch (e) {
      console.error("Accept failed:", e);
    }
  }

  async function handleComplete(taskId: string) {
    try {
      await completeTask(taskId);
    } catch (e) {
      console.error("Complete failed:", e);
    }
  }

  async function handleAbandon(taskId: string) {
    try {
      await abandonTask(taskId);
    } catch (e) {
      console.error("Abandon failed:", e);
    }
  }

  async function handleRequestRevision(taskId: string) {
    try {
      const resp = await fetch(`/api/tasks/${taskId}/request-revision`, { method: "PATCH" });
      await resp.json();
    } catch (e) {
      console.error("Request revision failed:", e);
    }
  }

  // Communicate / Improve - trigger via store → WorkbenchPanel
  function handleCommunicate(task: any) {
    const assignee = task.assignee || task.creator || "";
    // Map assignee name to agent id
    const agentMap: Record<string, string> = {
      "周华健": "zhouhuajian",
      "任贤齐": "renxianqi",
      "阿牛": "aniu",
      "周星驰": "zhouxingchi",
      "里德": "reed",
      "里德（Reed）": "reed",
      "苏珊": "susan",
      "果爸": "main",
    };
    let agentId = "";
    for (const [name, id] of Object.entries(agentMap)) {
      if (assignee.includes(name)) {
        agentId = id;
        break;
      }
    }
    if (!agentId) {
      agentId = assignee.toLowerCase().replace(/[^a-z0-9]/g, "");
    }
    const msg = `【沟通改进请求】\n任务ID: ${task.id}\n任务: ${task.title}\n当前状态: ${task.status}\n负责人: ${assignee}\n\n请查看该任务并沟通改进方案。`;
    communicateRequest.set({ agentId, message: msg });
  }

  // Load viewed tasks on mount
  loadViewedTasks();

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
    "pending-approval": 0,
    "in-progress": 1,
    "pending-acceptance": 2,
    pending: 3,
    assigned: 4,
    completed: 5,
    accepted: 6,
    rejected: 7,
  };
  const priorityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };

  $: sorted = (() => {
    viewedTasksVersion; // trigger dependency
    const result = [...filtered].sort((a, b) => {
      // NEW (unviewed) tasks always on top
      const aIsNew = !viewedTasks.has(a.id);
      const bIsNew = !viewedTasks.has(b.id);
    if (aIsNew && !bIsNew) return -1;
    if (!aIsNew && bIsNew) return 1;

    if (sortBy === "status") {
      return (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9);
    } else if (sortBy === "priority") {
      return (priorityOrder[a.priority] ?? 9) - (priorityOrder[b.priority] ?? 9);
    } else {
      // Use created_at instead of updated_at
      const aTime = a.created_at || a.updated_at || "";
      const bTime = b.created_at || b.updated_at || "";
      return bTime.localeCompare(aTime);
    }
    });
    return result;
  })();

  // Stats
  $: totalCount = $tasks.length;
  $: pendingApprovalCount = $tasks.filter(t => t.status === "pending-approval").length;
  $: pendingAcceptCount = $tasks.filter(t => t.status === "pending-acceptance").length;
  $: completedCount = $tasks.filter(t => t.status === "completed" || t.status === "accepted").length;
  $: rejectedCount = $tasks.filter(t => t.status === "rejected").length;
  $: otherCount = totalCount - pendingApprovalCount - pendingAcceptCount - completedCount - rejectedCount;

  // Helpers
  const statusLabel: Record<string, string> = {
    pending: "待分配", assigned: "已分配", "in-progress": "进行中",
    completed: "已完成", accepted: "已验收", "pending-approval": "待审批",
    "pending-acceptance": "待验收", rejected: "已驳回",
  };
  const statusClass: Record<string, string> = {
    pending: "status-pending", assigned: "status-in_progress",
    "in-progress": "status-in_progress", completed: "status-completed",
    accepted: "status-completed", "pending-approval": "status-pending",
    "pending-acceptance": "status-in_progress", rejected: "status-blocked",
  };
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
  <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
    <div class="glass-card p-4 space-y-1 text-center">
      <p class="font-orbitron text-2xl font-bold neon-cyan">{totalCount}</p>
      <p class="text-xs text-txt-secondary font-mono">总任务</p>
    </div>
    <div class="glass-card p-4 space-y-1 text-center">
      <p class="font-orbitron text-2xl font-bold text-cyber-amber">{pendingApprovalCount}</p>
      <p class="text-xs text-txt-secondary font-mono">待审批</p>
    </div>
    <div class="glass-card p-4 space-y-1 text-center">
      <p class="font-orbitron text-2xl font-bold neon-green">{completedCount}</p>
      <p class="text-xs text-txt-secondary font-mono">已完成</p>
    </div>
    <div class="glass-card p-4 space-y-1 text-center">
      <p class="font-orbitron text-2xl font-bold neon-amber">{pendingAcceptCount}</p>
      <p class="text-xs text-txt-secondary font-mono">待验收</p>
    </div>
    <div class="glass-card p-4 space-y-1 text-center">
      <p class="font-orbitron text-2xl font-bold text-cyber-red/60">{rejectedCount}</p>
      <p class="text-xs text-txt-secondary font-mono">已驳回</p>
    </div>
  </div>

  <!-- Filters -->
  <div class="glass-card p-4 flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-3">
    <div class="flex items-center gap-2 w-full sm:w-auto">
      <span class="text-xs font-mono text-txt-secondary shrink-0">使命:</span>
      <select bind:value={filterMission}
        class="flex-1 sm:flex-none bg-bg-light/40 border border-white/10 rounded px-2 py-1 text-xs font-mono text-txt-primary focus:border-cyber-cyan/40 focus:outline-none">
        <option value="">全部</option>
        {#each uniqueMissions as mid}
          <option value={mid}>{missionTitle(mid)}</option>
        {/each}
      </select>
    </div>
    <div class="flex items-center gap-2 w-full sm:w-auto">
      <span class="text-xs font-mono text-txt-secondary shrink-0">状态:</span>
      <select bind:value={filterStatus}
        class="flex-1 sm:flex-none bg-bg-light/40 border border-white/10 rounded px-2 py-1 text-xs font-mono text-txt-primary focus:border-cyber-cyan/40 focus:outline-none">
        <option value="">全部</option>
        <option value="pending">待分配</option>
        <option value="assigned">已分配</option>
        <option value="in-progress">进行中</option>
        <option value="pending-acceptance">待验收</option>
        <option value="pending-approval">待审批</option>
        <option value="completed">已完成</option>
        <option value="accepted">已验收</option>
        <option value="rejected">已驳回</option>
        <option value="archived">已归档</option>
      </select>
    </div>
    <div class="flex items-center gap-2 w-full sm:w-auto">
      <span class="text-xs font-mono text-txt-secondary shrink-0">负责人:</span>
      <select bind:value={filterAssignee}
        class="flex-1 sm:flex-none bg-bg-light/40 border border-white/10 rounded px-2 py-1 text-xs font-mono text-txt-primary focus:border-cyber-cyan/40 focus:outline-none">
        <option value="">全部</option>
        {#each uniqueAssignees as a}
          <option value={a}>{a}</option>
        {/each}
      </select>
    </div>
    <div class="flex items-center gap-2 w-full sm:w-auto">
      <span class="text-xs font-mono text-txt-secondary shrink-0">领域:</span>
      <select bind:value={filterDomain}
        class="flex-1 sm:flex-none bg-bg-light/40 border border-white/10 rounded px-2 py-1 text-xs font-mono text-txt-primary focus:border-cyber-cyan/40 focus:outline-none">
        <option value="">全部</option>
        {#each uniqueDomains as d}
          <option value={d}>{DOMAIN_LABELS[d] || d}</option>
        {/each}
      </select>
    </div>

    <div class="hidden sm:block flex-1"></div>

    <div class="flex items-center gap-2 w-full sm:w-auto">
      <span class="text-xs font-mono text-txt-secondary shrink-0">排序:</span>
      <button on:click={() => sortBy = "status"}
        class="px-2 py-1 rounded text-xs font-mono {sortBy === 'status' ? 'bg-cyber-cyan/20 text-cyber-cyan border border-cyber-cyan/30' : 'bg-bg-light/30 text-txt-secondary border border-white/10'} transition-colors">
        状态
      </button>
      <button on:click={() => sortBy = "time"}
        class="px-2 py-1 rounded text-xs font-mono {sortBy === 'time' ? 'bg-cyber-cyan/20 text-cyber-cyan border border-cyber-cyan/30' : 'bg-bg-light/30 text-txt-secondary border border-white/10'} transition-colors">
        时间
      </button>
      <span class="text-xs font-mono text-txt-secondary ml-2">{sorted.length} 条结果</span>
    </div>
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
                  <!-- NEW badge for unviewed tasks -->
                  {#if !isViewed(task.id)}
                    <span class="px-1.5 py-0.5 rounded text-xs bg-cyber-red/20 border border-cyber-red/30 text-cyber-red font-bold animate-pulse">NEW</span>
                  {/if}
                  <span class="status-badge {statusClass[task.status] || 'status-pending'} text-xs">
                    {statusLabel[task.status] || task.status}
                  </span>
                  {#if task.source_type}
                    <span class="px-1.5 py-0.5 rounded text-xs bg-cyber-violet/10 border border-cyber-violet/20 text-cyber-violet/80">
                      {sourceLabel[task.source_type] || task.source_type}
                    </span>
                  {/if}
                </div>
                <h3 class="font-rajdhani text-base font-semibold leading-tight">{task.title}</h3>
                <div class="flex items-center gap-3 mt-2 text-xs font-mono text-txt-secondary">
                  <span>👤 {task.assignee || task.creator || "—"}</span>
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
                <MarkdownDetail title="📋 任务描述" content={task.content} accentColor="cyan" initialOpen={true} />
              {/if}
              {#if task.proposal_content}
                <MarkdownDetail title="💡 提案内容" content={task.proposal_content} accentColor="amber" initialOpen={true} />
              {/if}
              {#if task.decision_detail}
                <MarkdownDetail
                  title="{task.decision_status === 'pending' ? '⏳ 待决策' : '✅ 已决策'}"
                  content={task.decision_detail}
                  accentColor={task.decision_status === 'pending' ? 'amber' : 'green'}
                  initialOpen={true}
                />
              {/if}

              <!-- Artifacts from content -->
              {#if parseArtifacts(task.content || task.proposal_content || '').length > 0}
                <div class="mt-3 p-3 rounded-lg bg-bg-mid/40 border border-white/5">
                  <p class="text-xs font-mono text-txt-secondary mb-2">📎 产出物</p>
                  <div class="space-y-1">
                    {#each parseArtifacts(task.content || task.proposal_content || '') as a}
                      <div class="flex items-center justify-between gap-2 text-xs">
                        <div class="flex items-center gap-2">
                          <span class="text-cyber-cyan">{a.name}</span>
                          {#if a.type}
                            <span class="px-1 py-0.5 rounded bg-white/5 text-txt-secondary">{a.type}</span>
                          {/if}
                        </div>
                        <div class="flex items-center gap-2">
                          {#if a.path.endsWith('.md')}
                            <button
                              class="px-2 py-0.5 rounded bg-cyber-cyan/10 border border-cyber-cyan/20 text-cyber-cyan hover:bg-cyber-cyan/20 transition-colors"
                              on:click|stopPropagation={() => openArtifactPreview(a)}
                            >
                              👁 预览
                            </button>
                          {/if}
                          <span class="text-txt-secondary/60 font-mono truncate max-w-[200px]" title={a.path}>{a.path}</span>
                        </div>
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}

              <!-- Phase Cards -->
              {#if phaseLoading}
                <div class="p-4 text-center text-txt-secondary text-xs">加载阶段信息...</div>
              {:else if phaseInfo.length > 0}
                <div class="mt-3 space-y-2">
                  <p class="text-xs font-mono text-txt-secondary mb-2">🚪 阶段门禁</p>
                  {#each phaseInfo as phase, idx}
                    <PhaseCard {task} {phase} isCurrentPhase={phase.status !== 'approved' && phase.status !== 'terminated'} />
                  {/each}
                </div>
              {/if}

              <!-- Discussion Panel -->
              {#if phaseInfo.length > 0}
                {@const currentPhase = phaseInfo.find(p => p.status === 'discussing' || p.status === 'pending-review')}
                {#if currentPhase}
                  <div class="mt-3">
                    <DiscussionPanel
                      taskId={task.id}
                      phaseId={currentPhase.id}
                      phaseLabel={currentPhase.label}
                      phaseStatus={currentPhase.status}
                      discussions={currentPhase.discussions || []}
                    />
                  </div>
                {/if}
              {/if}

              <!-- Action Buttons -->
              <div class="mt-4 pt-3 border-t border-white/5">
                {#if task.status === 'pending-approval'}
                  <div class="flex flex-wrap gap-2">
                    <button
                      class="px-4 py-2 rounded text-xs font-mono bg-cyber-green/15 border border-cyber-green/30 text-cyber-green hover:bg-cyber-green/25 transition-colors"
                      on:click|stopPropagation={() => handleApprove(task.id)}
                    >✅ 批准</button>
                    <button
                      class="px-3 py-2 rounded text-xs font-mono bg-cyber-red/10 border border-cyber-red/20 text-cyber-red/70 hover:bg-cyber-red/20 transition-colors"
                      on:click|stopPropagation={() => handleReject(task.id)}
                    >❌ 驳回</button>
                    <button
                      class="px-3 py-2 rounded text-xs font-mono bg-cyber-amber/10 border border-cyber-amber/20 text-cyber-amber/80 hover:bg-cyber-amber/20 transition-colors"
                      on:click|stopPropagation={() => handleCommunicate(task)}
                    >💬 沟通改进</button>
                  </div>
                {:else if task.status === 'in-progress'}
                  <div class="flex flex-wrap gap-2">
                    <button
                      class="px-4 py-2 rounded text-xs font-mono bg-cyber-green/15 border border-cyber-green/30 text-cyber-green hover:bg-cyber-green/25 transition-colors"
                      on:click|stopPropagation={() => handleComplete(task.id)}
                    >📋 提交验收</button>
                    <button
                      class="px-3 py-2 rounded text-xs font-mono bg-cyber-amber/10 border border-cyber-amber/20 text-cyber-amber/80 hover:bg-cyber-amber/20 transition-colors"
                      on:click|stopPropagation={() => handleCommunicate(task)}
                    >💬 沟通改进</button>
                  </div>
                {:else if task.status === 'pending-acceptance'}
                  <div class="flex flex-wrap gap-2">
                    <button
                      class="px-4 py-2 rounded text-xs font-mono bg-cyber-green/15 border border-cyber-green/30 text-cyber-green hover:bg-cyber-green/25 transition-colors"
                      on:click|stopPropagation={() => handleAccept(task.id)}
                    >✅ 验收通过</button>
                    <button
                      class="px-3 py-2 rounded text-xs font-mono bg-cyber-red/10 border border-cyber-red/20 text-cyber-red/70 hover:bg-cyber-red/20 transition-colors"
                      on:click|stopPropagation={() => handleRequestRevision(task.id)}
                    >↩️ 退回修改</button>
                    <button
                      class="px-3 py-2 rounded text-xs font-mono bg-cyber-amber/10 border border-cyber-amber/20 text-cyber-amber/80 hover:bg-cyber-amber/20 transition-colors"
                      on:click|stopPropagation={() => handleCommunicate(task)}
                    >💬 沟通改进</button>
                  </div>
                {:else if task.status === 'completed' || task.status === 'rejected'}
                  <!-- 终态，无操作按钮 -->
                {/if}
              </div>

              <div class="flex items-center gap-4 text-xs font-mono text-txt-secondary">
                <span>👤 负责人: <span class="text-cyber-amber">{task.assignee || task.creator || "—"}</span></span>
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

<!-- Preview Modal -->
{#if previewArtifact}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" on:click|stopPropagation={closePreview}>
    <div class="glass-card w-full max-w-3xl max-h-[80vh] overflow-hidden m-4" on:click|stopPropagation>
      <div class="flex items-center justify-between p-4 border-b border-white/5">
        <h3 class="font-rajdhani text-lg font-semibold">📄 {previewArtifact.name}</h3>
        <button
          class="w-8 h-8 rounded flex items-center justify-center bg-white/5 hover:bg-white/10 text-txt-secondary"
          on:click={closePreview}
        >
          ✕
        </button>
      </div>
      <div class="p-4 overflow-y-auto max-h-[60vh]">
        {#if previewLoading}
          <div class="text-center py-8 text-txt-secondary">加载中...</div>
        {:else if previewError}
          <div class="text-center py-8 text-cyber-red">{previewError}</div>
        {:else}
          <div class="markdown-body text-sm leading-relaxed">
            {@html renderMd(previewContent)}
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}
