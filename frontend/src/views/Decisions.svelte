<script lang="ts">
  import { decisions, tasks, loading, fetchAll } from "../lib/stores";
  import { approveTask, rejectTask, discussTask, acceptTask, requestTaskRevision } from "../lib/api";
  import MarkdownDetail from "../components/MarkdownDetail.svelte";

  let loadingTask: string | null = null;

  // ─── 果爸专属工作台：三件事 ───────────────────────────────
  $: proposals        = $tasks.filter((t: any) => t.status === "pending-approval");
  $: awaitingAccept   = $tasks.filter((t: any) => t.status === "pending-acceptance");
  $: discussingItems  = $decisions.filter((d: any) => d.decision_status === "discussing");

  $: totalAction = proposals.length + awaitingAccept.length + discussingItems.length;

  // ─── 操作 ────────────────────────────────────────────────
  async function op(taskId: string, fn: (id: string) => Promise<any>, label: string) {
    loadingTask = taskId;
    try {
      const r = await fn(taskId);
      if (!r.success) alert(`操作失败: ${r.error || "未知错误"}`);
      else await fetchAll();
    } catch (e) {
      alert(`操作失败: ${e}`);
    } finally {
      loadingTask = null;
    }
  }

  const handleApprove  = (id: string) => op(id, approveTask,           "通过");
  const handleReject   = (id: string) => op(id, rejectTask,            "驳回");
  const handleDiscuss = (id: string) => op(id, discussTask,            "讨论");
  const handleAccept  = (id: string) => op(id, acceptTask,             "验收通过");
  const handleRevise  = (id: string) => op(id, requestTaskRevision,    "打回修改");

  function isLoading(id: string) { return loadingTask === id; }
</script>

<div class="page-enter space-y-6">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <div>
      <h1 class="font-orbitron text-2xl font-bold neon-cyan flex items-center gap-2">
        <span>◈</span> 决策中心
      </h1>
      <p class="text-txt-secondary text-sm mt-1 font-chinese">
        果爸专属工作台 · {totalAction} 件待处理
      </p>
    </div>

    {#if totalAction > 0}
      <div class="glass-card px-4 py-2 flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-cyber-red pulse-glow"></span>
        <span class="text-cyber-red font-mono text-sm font-bold">{totalAction} 待处理</span>
      </div>
    {/if}
  </div>

  <!-- 空状态 -->
  {#if !$loading && totalAction === 0}
    <div class="glass-card glow-border p-16 text-center space-y-4">
      <div class="text-5xl">✨</div>
      <h2 class="font-rajdhani text-xl font-semibold neon-green">全部搞定！</h2>
      <p class="text-txt-secondary font-chinese">没有需要您拍板的事项，团队在高效运转 🎯</p>
    </div>

  {:else}

    <!-- ══ 迭代提案 — 待审批 ══════════════════════════════════ -->
    {#if proposals.length > 0}
      <div class="space-y-4">
        <h2 class="font-rajdhani text-lg font-semibold flex items-center gap-2">
          <span class="neon-amber">▸</span> 📋 迭代提案
          <span class="text-xs font-mono text-cyber-amber/60">等待审批 · {proposals.length}</span>
        </h2>
        {#each proposals as p}
          <div class="glass-card p-5 border-amber-500/30 hover:border-amber-500/50 transition-all">
            <div class="flex items-start gap-4">
              <!-- 标题区 -->
              <div class="flex-1 min-w-0 space-y-3">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-mono text-xs text-cyber-cyan/60">{p.id}</span>
                  {#if p.iteration_round}
                    <span class="px-2 py-0.5 rounded text-xs bg-amber-500/10 border border-amber-500/20 text-amber-400">
                      🔄 迭代第{p.iteration_round}轮
                    </span>
                  {/if}
                  {#if p.iteration_driver}
                    <span class="text-xs text-txt-secondary">提案人: <span class="text-amber-400">{p.iteration_driver}</span></span>
                  {/if}
                </div>
                <h3 class="font-rajdhani text-lg font-semibold">{p.title}</h3>

                {#if p.proposal_content}
                  <MarkdownDetail
                    title="💡 提案内容"
                    content={p.proposal_content}
                    accentColor="amber"
                    initialOpen={true}
                  />
                {/if}

                {#if p.judgment}
                  <MarkdownDetail title="📝 负责人判断" content={p.judgment} accentColor="violet" />
                {/if}

                <div class="flex items-center gap-3 text-xs font-mono text-txt-secondary">
                  <span>创建: {p.created_at}</span>
                  <span>负责人: {p.assignee || "待分配"}</span>
                </div>

                <!-- 操作按钮 -->
                <div class="flex items-center gap-3 pt-2 border-t border-white/5">
                  <button
                    class="px-4 py-2 rounded-lg bg-cyber-green/10 border border-cyber-green/30 text-cyber-green text-sm font-semibold hover:bg-cyber-green/20 transition-colors disabled:opacity-40"
                    disabled={isLoading(p.id)} on:click={() => handleApprove(p.id)}
                  >
                    {isLoading(p.id) ? "⏳..." : "✅ 通过"}
                  </button>
                  <button
                    class="px-4 py-2 rounded-lg bg-cyber-red/10 border border-cyber-red/30 text-cyber-red text-sm font-semibold hover:bg-cyber-red/20 transition-colors disabled:opacity-40"
                    disabled={isLoading(p.id)} on:click={() => handleReject(p.id)}
                  >
                    {isLoading(p.id) ? "⏳..." : "❌ 驳回"}
                  </button>
                  <button
                    class="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-txt-secondary text-sm hover:text-txt-primary hover:border-white/20 transition-colors disabled:opacity-40"
                    disabled={isLoading(p.id)} on:click={() => handleDiscuss(p.id)}
                  >
                    💬 讨论
                  </button>
                </div>
              </div>
            </div>
          </div>
        {/each}
      </div>
    {/if}

    <!-- ══ 待验收 ════════════════════════════════════════════ -->
    {#if awaitingAccept.length > 0}
      <div class="space-y-4">
        <h2 class="font-rajdhani text-lg font-semibold flex items-center gap-2">
          <span class="neon-violet">▸</span> 🔍 待验收
          <span class="text-xs font-mono text-violet-400/60">等待您验收 · {awaitingAccept.length}</span>
        </h2>
        {#each awaitingAccept as t}
          <div class="glass-card p-5 border-violet-500/30 hover:border-violet-500/50 transition-all">
            <div class="flex items-start gap-4">
              <div class="flex-1 min-w-0 space-y-3">
                <div class="flex items-center gap-2">
                  <span class="font-mono text-xs text-cyber-cyan/60">{t.id}</span>
                  <span class="text-xs text-txt-secondary">负责人: {t.assignee}</span>
                </div>
                <h3 class="font-rajdhani text-lg font-semibold">{t.title}</h3>

                {#if t.content}
                  <MarkdownDetail title="📋 任务描述" content={t.content} accentColor="violet" />
                {/if}

                <div class="flex items-center gap-3 pt-2 border-t border-white/5">
                  <button
                    class="px-4 py-2 rounded-lg bg-cyber-green/10 border border-cyber-green/30 text-cyber-green text-sm font-semibold hover:bg-cyber-green/20 transition-colors disabled:opacity-40"
                    disabled={isLoading(t.id)} on:click={() => handleAccept(t.id)}
                  >
                    {isLoading(t.id) ? "⏳..." : "✅ 验收通过"}
                  </button>
                  <button
                    class="px-4 py-2 rounded-lg bg-cyber-red/10 border border-cyber-red/30 text-cyber-red text-sm font-semibold hover:bg-cyber-red/20 transition-colors disabled:opacity-40"
                    disabled={isLoading(t.id)} on:click={() => handleRevise(t.id)}
                  >
                    {isLoading(t.id) ? "⏳..." : "❌ 打回修改"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        {/each}
      </div>
    {/if}

    <!-- ══ 讨论中 ══════════════════════════════════════════════ -->
    {#if discussingItems.length > 0}
      <div class="space-y-4">
        <h2 class="font-rajdhani text-lg font-semibold flex items-center gap-2">
          <span class="neon-cyan">▸</span> 💬 讨论中
          <span class="text-xs font-mono text-cyber-cyan/60">需要您参与讨论 · {discussingItems.length}</span>
        </h2>
        {#each discussingItems as d}
          <div class="glass-card p-5 border-cyber-cyan/20 hover:border-cyber-cyan/40 transition-all">
            <div class="flex items-start gap-4">
              <div class="flex-1 min-w-0 space-y-3">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-mono text-xs text-cyber-cyan/60">{d.task_id || d.id}</span>
                  <span class="px-2 py-0.5 rounded text-xs bg-cyber-cyan/10 border border-cyber-cyan/20 text-cyber-cyan/80">
                    💬 讨论中
                  </span>
                  {#if d.priority}
                    <span class="text-xs text-txt-secondary">优先级: {d.priority}</span>
                  {/if}
                </div>
                <h3 class="font-rajdhani text-lg font-semibold">{d.title}</h3>

                {#if d.task_content}
                  <MarkdownDetail title="📋 任务描述" content={d.task_content} accentColor="cyan" />
                {/if}

                {#if d.decision_detail}
                  <MarkdownDetail title="💬 讨论记录" content={d.decision_detail} accentColor="cyan" />
                {/if}

                {#if d.proposal_content}
                  <MarkdownDetail title="💡 提案内容" content={d.proposal_content} accentColor="amber" />
                {/if}

                <div class="flex items-center gap-3 text-xs font-mono text-txt-secondary">
                  <span>负责人: {d.assignee}</span>
                  <span>创建: {d.created_at}</span>
                </div>

                <div class="flex items-center gap-3 pt-2 border-t border-white/5">
                  <button
                    class="px-4 py-2 rounded-lg bg-cyber-green/10 border border-cyber-green/30 text-cyber-green text-sm font-semibold hover:bg-cyber-green/20 transition-colors disabled:opacity-40"
                    disabled={isLoading(d.task_id || d.id)} on:click={() => handleApprove(d.task_id || d.id)}
                  >
                    {isLoading(d.task_id || d.id) ? "⏳..." : "✅ 拍板通过"}
                  </button>
                  <button
                    class="px-4 py-2 rounded-lg bg-cyber-red/10 border border-cyber-red/30 text-cyber-red text-sm font-semibold hover:bg-cyber-red/20 transition-colors disabled:opacity-40"
                    disabled={isLoading(d.task_id || d.id)} on:click={() => handleReject(d.task_id || d.id)}
                  >
                    {isLoading(d.task_id || d.id) ? "⏳..." : "❌ 终止"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        {/each}
      </div>
    {/if}

  {/if}
</div>
