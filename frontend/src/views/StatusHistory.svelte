<script lang="ts">
  import { onMount } from "svelte";
  import { fetchStatusHistory } from "../lib/api";
  import type { StatusReport } from "../lib/api";
  import { showHistorySidebar, statusDetailAgent, statusHistory, statusHistoryLoading } from "../lib/stores";

  let filterAgent = "";
  let filterType = "";
  let page = 1;
  let total = 0;

  $: show = $showHistorySidebar;

  function close() {
    showHistorySidebar.set(false);
    statusDetailAgent.set(null);
    filterAgent = "";
    filterType = "";
    page = 1;
  }

  async function loadHistory() {
    statusHistoryLoading.set(true);
    try {
      const params: any = { page, limit: 20 };
      if ($statusDetailAgent) params.agent_id = $statusDetailAgent;
      if (filterAgent) params.agent_id = filterAgent;
      if (filterType) params.type = filterType;
      const res = await fetchStatusHistory(params);
      statusHistory.set(res.records);
      total = res.total;
    } catch (e) {
      console.error("Failed to load history:", e);
    } finally {
      statusHistoryLoading.set(false);
    }
  }

  $: if (show) {
    if ($statusDetailAgent && !filterAgent) {
      filterAgent = $statusDetailAgent;
    }
    loadHistory();
  }

  $: if (filterAgent || filterType) {
    page = 1;
  }

  function typeIcon(type: string): string {
    if (type === "difficulty") return "🚨";
    if (type === "decision") return "🔔";
    return "🟢";
  }

  function typeLabel(type: string): string {
    if (type === "difficulty") return "困难";
    if (type === "decision") return "决策";
    return "汇报";
  }

  function timeAgo(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "刚刚";
    if (mins < 60) return `${mins}分钟前`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}小时前`;
    return `${Math.floor(hours / 24)}天前`;
  }

  const agentNames: Record<string, string> = {
    susan: "苏珊",
    reed: "里德",
    guoba: "果爸",
  };
</script>

{#if show}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="fixed inset-0 z-40 flex justify-end" on:click={close}>
    <div class="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>

    <div class="relative w-full max-w-md glass-card border-l border-cyber-cyan/10 overflow-y-auto" on:click|stopPropagation>
      <!-- Header -->
      <div class="sticky top-0 bg-bg-mid/90 backdrop-blur-md p-5 border-b border-white/5">
        <div class="flex items-center justify-between mb-4">
          <h2 class="font-rajdhani text-lg font-bold flex items-center gap-2">
            <span>📋</span> 汇报历史
          </h2>
          <button on:click={close} class="text-txt-secondary hover:text-txt-primary text-xl">✕</button>
        </div>

        <!-- Filters -->
        <div class="flex gap-2 flex-wrap">
          <select bind:value={filterAgent} class="bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-txt-primary focus:outline-none">
            <option value="">全部员工</option>
            <option value="susan">苏珊</option>
            <option value="reed">里德</option>
            <option value="guoba">果爸</option>
          </select>
          <select bind:value={filterType} class="bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-txt-primary focus:outline-none">
            <option value="">全部类型</option>
            <option value="report">汇报</option>
            <option value="difficulty">困难</option>
            <option value="decision">决策</option>
          </select>
          <span class="text-xs font-mono text-txt-secondary ml-auto self-center">
            {total} 条记录
          </span>
        </div>
      </div>

      <!-- List -->
      <div class="p-3 space-y-2">
        {#if $statusHistoryLoading}
          {#each Array(3) as _}
            <div class="p-4 rounded-lg bg-white/3 animate-pulse h-24"></div>
          {/each}
        {:else if $statusHistory.length === 0}
          <div class="text-center py-12 text-txt-secondary text-sm font-chinese">
            暂无汇报记录
          </div>
        {:else}
          {#each $statusHistory as record}
            <div class="p-3 rounded-lg bg-white/3 border border-white/5 hover:border-cyber-cyan/20 transition-colors">
              <div class="flex items-center justify-between mb-1.5">
                <div class="flex items-center gap-2">
                  <span>{typeIcon(record.type)}</span>
                  <span class="text-sm font-medium text-txt-primary">
                    {agentNames[record.agent_id] || record.agent_id}
                  </span>
                  <span class="text-xs px-1.5 py-0.5 rounded bg-white/5 text-txt-secondary">
                    {typeLabel(record.type)}
                  </span>
                </div>
                <span class="text-xs font-mono text-txt-secondary">
                  {timeAgo(record.created_at)}
                </span>
              </div>

              <p class="text-xs font-chinese text-txt-secondary leading-relaxed">
                {#if record.current_task}
                  <span class="text-cyber-cyan/80">进度：</span>{record.progress_detail || record.current_task}
                {/if}
                {#if record.difficulty}
                  <br /><span class="text-cyber-red/80">问题：</span>{record.difficulty}
                {/if}
                {#if record.needs_decision}
                  <br /><span class="text-cyber-amber/80">决策：</span>{record.needs_decision}
                {/if}
                {#if record.needs_help}
                  <br /><span class="text-cyber-violet/80">需求：</span>{record.needs_help}
                {/if}
              </p>

              {#if record.task_id}
                <p class="text-xs font-mono text-txt-secondary/50 mt-1.5">
                  📎 {record.task_id}
                </p>
              {/if}
            </div>
          {/each}
        {/if}

        <!-- Pagination -->
        {#if total > 20}
          <div class="flex justify-center gap-2 pt-3">
            <button
              on:click={() => (page = Math.max(1, page - 1))}
              disabled={page <= 1}
              class="text-xs px-3 py-1.5 rounded border border-white/10 text-txt-secondary disabled:opacity-30 hover:border-cyber-cyan/20"
            >
              ← 上一页
            </button>
            <span class="text-xs font-mono text-txt-secondary self-center">{page}</span>
            <button
              on:click={() => (page = page + 1)}
              disabled={page * 20 >= total}
              class="text-xs px-3 py-1.5 rounded border border-white/10 text-txt-secondary disabled:opacity-30 hover:border-cyber-cyan/20"
            >
              下一页 →
            </button>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}
