<script lang="ts">
  import { onMount } from "svelte";
  import { tasks } from "../../lib/stores";
  import { fetchFileContent, acceptTask, archiveTask, completeTask, abandonTask } from "../../lib/api";

  // ─── Filter ──────────────────────────────────────────────────────────
  type FilterTab = "all" | "pending-approval" | "in-progress" | "completed";
  let filterTab: FilterTab = "all";

  // ─── Detail view ─────────────────────────────────────────────────────
  let detailTask: any | null = null;

  // ─── Artifact preview ────────────────────────────────────────────────
  let previewContent = "";
  let previewLoading = false;
  let previewError = "";
  let previewName = "";
  let showPreview = false;

  // ─── Viewed tasks ────────────────────────────────────────────────────
  const VIEWED_KEY = "synapse_viewed_tasks";
  function getViewedSet(): Set<string> {
    try { return new Set(JSON.parse(localStorage.getItem(VIEWED_KEY) || "[]")); } catch { return new Set(); }
  }
  function markViewed(id: string) {
    const s = getViewedSet(); s.add(id);
    localStorage.setItem(VIEWED_KEY, JSON.stringify([...s]));
    viewedTasks = s;
  }
  let viewedTasks = getViewedSet();

  // ─── Derived ─────────────────────────────────────────────────────────
  $: filtered = ($tasks || []).filter((t: any) => {
    if (filterTab === "all") return true;
    if (filterTab === "pending-approval") {
      const s = (t.status || "").toLowerCase();
      return s === "pending-approval" || s === "待审批";
    }
    if (filterTab === "in-progress") {
      const s = (t.status || "").toLowerCase();
      return s === "in-progress" || s === "进行中";
    }
    if (filterTab === "completed") {
      const s = (t.status || "").toLowerCase();
      return s === "completed" || s === "已完成" || s === "accepted" || s === "已验收";
    }
    return true;
  });

  function statusColor(status: string): string {
    const s = (status || "").toLowerCase();
    if (s === "in-progress" || s === "进行中") return "#00E5FF";
    if (s === "pending-approval" || s === "待审批") return "#FFB800";
    if (s === "completed" || s === "已完成") return "#00FF88";
    if (s === "accepted" || s === "已验收") return "#00FF88";
    if (s === "rejected" || s === "已驳回") return "#FF3860";
    if (s === "pending-acceptance" || s === "待验收") return "#7C3AED";
    return "#64748B";
  }

  function statusLabel(status: string): string {
    const map: Record<string, string> = {
      "in-progress": "进行中", "进行中": "进行中",
      "pending-approval": "待审批", "待审批": "待审批",
      "completed": "已完成", "已完成": "已完成",
      "accepted": "已验收", "已验收": "已验收",
      "rejected": "已驳回", "已驳回": "已驳回",
      "pending-acceptance": "待验收", "待验收": "待验收",
      "pending": "待分配", "assigned": "已分配",
    };
    return map[(status || "").toLowerCase()] || status;
  }

  function priorityColor(p: string): string {
    if (p === "high") return "#FF3860";
    if (p === "medium") return "#FFB800";
    return "#64748B";
  }

  function isNew(task: any): boolean {
    return !viewedTasks.has(task.id);
  }

  function openDetail(task: any) {
    detailTask = task;
    markViewed(task.id);
  }

  function closeDetail() {
    detailTask = null;
    showPreview = false;
    previewContent = "";
  }

  async function openArtifact(artifact: any) {
    showPreview = true;
    previewName = artifact.name;
    previewContent = "";
    previewError = "";
    previewLoading = true;
    try {
      const res = await fetchFileContent(artifact.path);
      previewContent = res.content || "";
      if (!previewContent) previewError = (res as any).error || "无法读取文件";
    } catch (e: any) {
      previewError = e.message || "加载失败";
    } finally {
      previewLoading = false;
    }
  }

  interface Artifact { name: string; type: string; path: string; time?: string; }
  function parseArtifacts(content: string): Artifact[] {
    if (!content) return [];
    const artifacts: Artifact[] = [];
    const p1 = /-\s*\*\*([^*]+)\*\*\s*\((\w+)\):\s*`([^`]+\.md)`\s*(?:—|-)\s*([^\n]+)/g;
    let m;
    while ((m = p1.exec(content)) !== null) artifacts.push({ name: m[1].trim(), type: m[2], path: m[3], time: m[4].trim() });
    const p2 = /-\s*\*\*([^*]+)\*\*:\s*`([^`]+\.md)`/g;
    while ((m = p2.exec(content)) !== null) { if (!artifacts.some(a => a.path === m[2])) artifacts.push({ name: m[1].trim(), type: "DOC", path: m[2] }); }
    const p3 = /\|\s*产出\s*\|\s*`([^`]+\.md)`/g;
    while ((m = p3.exec(content)) !== null) { if (!artifacts.some(a => a.path === m[1])) artifacts.push({ name: m[1].split("/").pop() || m[1], type: "DOC", path: m[1] }); }
    const p4 = /[-*]\s*[^\n`]*`([^`]+\.md)`/g;
    while ((m = p4.exec(content)) !== null) { if (!artifacts.some(a => a.path === m[1])) artifacts.push({ name: m[1].split("/").pop() || m[1], type: "DOC", path: m[1] }); }
    const p5 = /`([^`]+\.md)`/g;
    while ((m = p5.exec(content)) !== null) { if (!artifacts.some(a => a.path === m[1])) artifacts.push({ name: m[1].split("/").pop() || m[1], type: "DOC", path: m[1] }); }
    return artifacts;
  }

  // ─── Task actions ─────────────────────────────────────────────────────
  let actionLoading = false;
  let actionMsg = "";

  async function doAction(fn: () => Promise<any>, label: string) {
    if (actionLoading) return;
    actionLoading = true;
    actionMsg = "";
    try {
      const r = await fn();
      if (r.success !== false) {
        actionMsg = `✅ ${label}成功`;
        // Refresh tasks
        try {
          const res = await fetch("/api/tasks");
          if (res.ok) tasks.set(await res.json());
        } catch (e) { console.error("[mobile] refresh failed:", e); }
        setTimeout(() => { actionMsg = ""; closeDetail(); }, 800);
      } else {
        actionMsg = `❌ ${r.error || label + "失败"}`;
        setTimeout(() => { actionMsg = ""; }, 3000);
      }
    } catch (e: any) {
      actionMsg = `❌ ${e.message || label + "失败"}`;
      setTimeout(() => { actionMsg = ""; }, 3000);
    } finally {
      actionLoading = false;
    }
  }

  // ─── Markdown mini renderer ───────────────────────────────────────────
  function parseMarkdown(text: string): string {
    if (!text) return "";
    return text
      .replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre style="background:rgba(0,0,0,0.4);padding:8px;border-radius:6px;overflow-x:auto;margin:6px 0;font-size:12px;white-space:pre-wrap;"><code>$2</code></pre>')
      .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#fff;">$1</strong>')
      .replace(/`(.+?)`/g, '<code style="background:rgba(0,0,0,0.3);padding:1px 4px;border-radius:3px;font-size:12px;">$1</code>')
      .replace(/^### (.+)$/gm, '<div style="font-size:14px;font-weight:700;color:#fff;margin:10px 0 4px;">$1</div>')
      .replace(/^## (.+)$/gm, '<div style="font-size:15px;font-weight:700;color:#fff;margin:12px 0 6px;">$1</div>')
      .replace(/^# (.+)$/gm, '<div style="font-size:16px;font-weight:700;color:#fff;margin:14px 0 6px;">$1</div>')
      .replace(/^- (.+)$/gm, '<div style="padding-left:10px;margin:2px 0;">• $1</div>')
      .replace(/\n/g, "<br/>");
  }

  const filterTabs: { id: FilterTab; label: string }[] = [
    { id: "all",              label: "全部" },
    { id: "pending-approval", label: "待审批" },
    { id: "in-progress",      label: "进行中" },
    { id: "completed",        label: "已完成" },
  ];
</script>

<div class="tasks-root">
  {#if showPreview && detailTask}
    <!-- ─── Artifact MD Preview ───────────── -->
    <div class="preview-overlay">
      <div class="preview-header">
        <button class="back-btn" on:click={() => { showPreview = false; previewContent = ""; }}>←</button>
        <span class="preview-title">{previewName}</span>
      </div>
      <div class="preview-body">
        {#if previewLoading}
          <div class="center-tip">加载中...</div>
        {:else if previewError}
          <div class="center-tip err">{previewError}</div>
        {:else}
          <div class="md-content">{@html parseMarkdown(previewContent)}</div>
        {/if}
      </div>
    </div>

  {:else if detailTask}
    <!-- ─── Task Detail ───────────────────── -->
    <div class="detail-overlay">
      <div class="detail-header">
        <button class="back-btn" on:click={closeDetail}>←</button>
        <span class="detail-title">{detailTask.title}</span>
      </div>

      <div class="detail-body">
        <!-- 基本信息 -->
        <div class="detail-meta">
          <span class="status-pill" style="background:{statusColor(detailTask.status)}22;color:{statusColor(detailTask.status)};border:1px solid {statusColor(detailTask.status)}44;">
            {statusLabel(detailTask.status)}
          </span>
          {#if detailTask.priority}
            <span class="priority-dot" style="background:{priorityColor(detailTask.priority)};"></span>
            <span style="font-size:12px;color:#94A3B8;">{detailTask.priority}</span>
          {/if}
          {#if detailTask.assignee}
            <span style="font-size:12px;color:#94A3B8;">@{detailTask.assignee}</span>
          {/if}
        </div>

        <!-- 任务内容 -->
        {#if detailTask.task_content || detailTask.content}
          <div class="detail-section">
            <div class="section-title">任务说明</div>
            <div class="md-content">{@html parseMarkdown(detailTask.task_content || detailTask.content || "")}</div>
          </div>
        {/if}

        <!-- 提案内容 -->
        {#if detailTask.proposal_content}
          <div class="detail-section">
            <div class="section-title">执行方案</div>
            <div class="md-content">{@html parseMarkdown(detailTask.proposal_content)}</div>
          </div>
        {/if}

        <!-- 产出物 (from phases) -->
        {#if detailTask.phases}
          {#each Object.values(detailTask.phases) as phase}
            {#if phase && phase.artifacts && phase.artifacts.length > 0}
              <div class="detail-section">
                <div class="section-title">产出物 — {phase.label || phase.id}</div>
                {#each phase.artifacts as artifact}
                  <button class="artifact-item" on:click={() => openArtifact(artifact)}>
                    <span class="artifact-icon">📄</span>
                    <span class="artifact-name">{artifact.name}</span>
                    <span class="artifact-arrow">›</span>
                  </button>
                {/each}
              </div>
            {/if}
          {/each}
        {/if}

        <!-- 产出物 (parsed from content) -->
        {#if parseArtifacts(detailTask.content || detailTask.proposal_content || '').length > 0}
          <div class="detail-section">
            <div class="section-title">📎 产出物</div>
            {#each parseArtifacts(detailTask.content || detailTask.proposal_content || '') as artifact}
              <button class="artifact-item" on:click={() => openArtifact(artifact)}>
                <span class="artifact-icon">📄</span>
                <span class="artifact-name">{artifact.name || artifact.path.split('/').pop()}</span>
                <span class="artifact-type">{artifact.type}</span>
                <span class="artifact-arrow">›</span>
              </button>
            {/each}
          </div>
        {/if}

        {#if actionMsg}
          <div class="action-msg">{actionMsg}</div>
        {/if}
      </div>

      <!-- 底部操作栏 -->
      <div class="detail-actions">
        {#if (detailTask.status || "") !== "archived" && (detailTask.status || "") !== "completed" && (detailTask.status || "") !== "accepted"}
          <button class="action-btn approve" disabled={actionLoading}
            on:click={() => doAction(() => acceptTask(detailTask.id), "提交成功")}>
            ✅ 提交成功
          </button>
        {/if}

        {#if (detailTask.status || "") !== "archived" && (detailTask.status || "") !== "completed" && (detailTask.status || "") !== "accepted"}
          <button class="action-btn reject" disabled={actionLoading}
            on:click={() => doAction(() => abandonTask(detailTask.id), "废弃")}>
            🚫 废弃
          </button>
        {/if}
      </div>
    </div>

  {:else}
    <!-- ─── Task List ──────────────────────── -->
    <div class="filter-tabs">
      {#each filterTabs as ft}
        <button
          class="filter-tab {filterTab === ft.id ? 'active' : ''}"
          on:click={() => { filterTab = ft.id; }}
        >{ft.label}</button>
      {/each}
    </div>

    <div class="task-list">
      {#if filtered.length === 0}
        <div class="empty-tip">暂无任务</div>
      {/if}
      {#each filtered as task}
        <button class="task-card" on:click={() => openDetail(task)}>
          <div class="task-status-bar" style="background:{statusColor(task.status)};"></div>
          <div class="task-card-body">
            <div class="task-card-header">
              <span class="task-title">{task.title}</span>
              {#if isNew(task)}
                <span class="new-badge">NEW</span>
              {/if}
            </div>
            <div class="task-card-meta">
              <span class="status-pill small" style="background:{statusColor(task.status)}22;color:{statusColor(task.status)};">
                {statusLabel(task.status)}
              </span>
              {#if task.assignee}
                <span class="meta-text">@{task.assignee}</span>
              {/if}
              {#if task.domain}
                <span class="meta-text">{task.domain}</span>
              {/if}
            </div>
          </div>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .tasks-root {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    background: #0B101E;
    overflow: hidden;
  }

  /* ─── Filter Tabs ────────────────────────── */
  .filter-tabs {
    display: flex;
    overflow-x: auto;
    border-bottom: 1px solid rgba(0,229,255,0.1);
    flex-shrink: 0;
    scrollbar-width: none;
  }
  .filter-tabs::-webkit-scrollbar { display: none; }

  .filter-tab {
    flex-shrink: 0;
    padding: 11px 16px;
    background: none;
    border: none;
    color: #94A3B8;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.15s;
    min-height: 44px;
    white-space: nowrap;
  }

  .filter-tab.active {
    color: #00E5FF;
    border-bottom-color: #00E5FF;
  }

  /* ─── Task List ──────────────────────────── */
  .task-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  }

  .task-card {
    display: flex;
    width: 100%;
    background: none;
    border: none;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    cursor: pointer;
    text-align: left;
    color: inherit;
    font-family: inherit;
    padding: 0;
    transition: background 0.12s;
    min-height: 60px;
  }

  .task-card:active {
    background: rgba(255,255,255,0.04);
  }

  .task-status-bar {
    width: 4px;
    flex-shrink: 0;
    border-radius: 0 2px 2px 0;
  }

  .task-card-body {
    flex: 1;
    padding: 12px 14px;
    min-width: 0;
  }

  .task-card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }

  .task-title {
    flex: 1;
    font-size: 15px;
    font-weight: 600;
    color: #E2E8F0;
    line-height: 1.3;
    word-break: break-word;
  }

  .new-badge {
    background: #FF3860;
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    flex-shrink: 0;
  }

  .task-card-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .status-pill {
    display: inline-block;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
  }

  .status-pill.small {
    font-size: 11px;
    padding: 2px 6px;
  }

  .meta-text {
    font-size: 12px;
    color: #64748B;
  }

  .priority-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .empty-tip {
    text-align: center;
    padding: 60px 20px;
    color: #475569;
    font-size: 14px;
  }

  /* ─── Detail / Preview Overlay ──────────── */
  .detail-overlay,
  .preview-overlay {
    position: absolute;
    inset: 0;
    background: #0B101E;
    display: flex;
    flex-direction: column;
    z-index: 10;
    overflow: hidden;
  }

  .detail-header,
  .preview-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    border-bottom: 1px solid rgba(0,229,255,0.1);
    background: rgba(11,16,30,0.98);
    flex-shrink: 0;
    min-height: 50px;
  }

  .back-btn {
    background: none;
    border: none;
    color: #00E5FF;
    font-size: 20px;
    cursor: pointer;
    min-width: 44px;
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
  }

  .detail-title,
  .preview-title {
    flex: 1;
    font-size: 15px;
    font-weight: 600;
    color: #E2E8F0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .detail-body,
  .preview-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .detail-meta {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .detail-section {
    background: rgba(17,24,39,0.6);
    border: 1px solid rgba(0,229,255,0.1);
    border-radius: 10px;
    padding: 14px;
  }

  .section-title {
    font-size: 12px;
    font-weight: 600;
    color: #00E5FF;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 10px;
  }

  .artifact-item {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 10px 12px;
    background: rgba(0,229,255,0.04);
    border: 1px solid rgba(0,229,255,0.1);
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 6px;
    min-height: 44px;
    text-align: left;
    color: inherit;
    font-family: inherit;
  }

  .artifact-icon { font-size: 16px; flex-shrink: 0; }

  .artifact-name {
    flex: 1;
    font-size: 14px;
    color: #E2E8F0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .artifact-type {
    font-size: 11px;
    color: #64748B;
    flex-shrink: 0;
  }

  .artifact-arrow {
    font-size: 18px;
    color: #00E5FF;
    flex-shrink: 0;
  }

  .action-msg {
    font-size: 13px;
    padding: 8px 12px;
    border-radius: 8px;
    background: rgba(0,229,255,0.06);
    color: #94A3B8;
    text-align: center;
  }

  /* ─── Bottom Action Bar ──────────────────── */
  .detail-actions {
    display: flex;
    gap: 10px;
    padding: 12px 16px;
    border-top: 1px solid rgba(0,229,255,0.1);
    flex-shrink: 0;
    padding-bottom: max(12px, env(safe-area-inset-bottom, 12px));
  }

  .action-btn {
    flex: 1;
    padding: 14px;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    min-height: 48px;
    transition: all 0.15s;
    border: none;
  }

  .action-btn.approve {
    background: rgba(0, 255, 136, 0.15);
    color: #00FF88;
    border: 1px solid rgba(0,255,136,0.3);
  }

  .action-btn.reject {
    background: rgba(255, 56, 96, 0.15);
    color: #FF3860;
    border: 1px solid rgba(255,56,96,0.3);
  }

  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* ─── MD Content ─────────────────────────── */
  .md-content {
    font-size: 14px;
    color: #CBD5E1;
    line-height: 1.7;
    word-break: break-word;
  }

  .center-tip {
    text-align: center;
    color: #64748B;
    padding: 40px 20px;
    font-size: 14px;
  }

  .center-tip.err { color: #FF3860; }
</style>
