<script lang="ts">
  import { postStatusReport } from "../lib/api";
  import { showDifficultyModal, statusDetailAgent } from "../lib/stores";

  let difficultyType = "技术难点";
  let severity = "minor";
  let description = "";
  let task_id = "";
  let resolution = "";
  let submitting = false;
  let success = false;

  $: agentId = $statusDetailAgent;

  function close() {
    showDifficultyModal.set(false);
    statusDetailAgent.set(null);
    // Reset form
    description = "";
    resolution = "";
    severity = "minor";
    difficultyType = "技术难点";
    success = false;
  }

  async function submit() {
    if (!description.trim() || !agentId) return;
    submitting = true;

    const agentNames: Record<string, string> = {
      susan: "苏珊",
      reed: "里德",
      guoba: "果爸",
    };

    const roles: Record<string, string> = {
      susan: "主设计师",
      reed: "开发者",
      guoba: "董事长",
    };

    try {
      await postStatusReport({
        agent_id: agentId,
        agent_name: agentNames[agentId] || agentId,
        role: roles[agentId] || "",
        difficulty: `[${difficultyType}] ${description}`,
        difficulty_level: severity as "none" | "minor" | "blocking",
        needs_help: resolution || undefined,
        task_id: task_id,
        type: "difficulty",
      });
      success = true;
      setTimeout(close, 1500);
    } catch (e) {
      console.error("Failed to report difficulty:", e);
    } finally {
      submitting = false;
    }
  }
</script>

{#if $showDifficultyModal}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4" on:click={close}>
    <div class="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>

    <div class="relative glass-card border border-cyber-red/20 w-full max-w-lg p-6" on:click|stopPropagation>
      <!-- Header -->
      <div class="flex items-center justify-between mb-5">
        <h2 class="font-rajdhani text-lg font-bold flex items-center gap-2">
          <span class="text-cyber-red">🚨</span> 上报困难
          {#if agentId}
            <span class="text-txt-secondary text-sm">— {$statusDetailAgent}</span>
          {/if}
        </h2>
        <button on:click={close} class="text-txt-secondary hover:text-txt-primary text-xl">✕</button>
      </div>

      {#if success}
        <div class="text-center py-8">
          <p class="text-3xl mb-3">✅</p>
          <p class="font-chinese text-cyber-green">上报成功！果爸会尽快处理</p>
        </div>
      {:else}
        <!-- Form -->
        <div class="space-y-4">
          <!-- Difficulty Type -->
          <div>
            <label class="text-xs font-mono text-txt-secondary block mb-1.5">困难类型</label>
            <div class="flex gap-2">
              {#each ["技术难点", "需要其他团队", "需要果爸决策"] as t}
                <button
                  on:click={() => (difficultyType = t)}
                  class="text-xs px-3 py-1.5 rounded border transition-colors {difficultyType === t
                    ? 'border-cyber-cyan bg-cyber-cyan/10 text-cyber-cyan'
                    : 'border-white/10 text-txt-secondary hover:border-white/20'}"
                >
                  {t}
                </button>
              {/each}
            </div>
          </div>

          <!-- Severity -->
          <div>
            <label class="text-xs font-mono text-txt-secondary block mb-1.5">紧急程度</label>
            <div class="flex gap-2">
              {#each [{v: "minor", l: "⚡ 一般"}, {v: "blocking", l: "🚨 阻塞"}] as s}
                <button
                  on:click={() => (severity = s.v)}
                  class="text-xs px-3 py-1.5 rounded border transition-colors {severity === s.v
                    ? severity === 'blocking'
                      ? 'border-cyber-red bg-cyber-red/10 text-cyber-red'
                      : 'border-cyber-amber bg-cyber-amber/10 text-cyber-amber'
                    : 'border-white/10 text-txt-secondary hover:border-white/20'}"
                >
                  {s.l}
                </button>
              {/each}
            </div>
          </div>

          <!-- Task ID -->
          <div>
            <label class="text-xs font-mono text-txt-secondary block mb-1.5">关联任务</label>
            <input
              bind:value={task_id}
              placeholder="task-xxx（可选）"
              class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-txt-primary placeholder:text-txt-secondary/40 focus:border-cyber-cyan/40 focus:outline-none"
            />
          </div>

          <!-- Description -->
          <div>
            <label class="text-xs font-mono text-txt-secondary block mb-1.5">困难描述</label>
            <textarea
              bind:value={description}
              rows="3"
              placeholder="描述你遇到的困难..."
              class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-txt-primary placeholder:text-txt-secondary/40 focus:border-cyber-cyan/40 focus:outline-none resize-none font-chinese"
            ></textarea>
          </div>

          <!-- Resolution -->
          <div>
            <label class="text-xs font-mono text-txt-secondary block mb-1.5">希望如何解决（可选）</label>
            <textarea
              bind:value={resolution}
              rows="2"
              placeholder="你希望谁来协助？需要什么资源？"
              class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm text-txt-primary placeholder:text-txt-secondary/40 focus:border-cyber-cyan/40 focus:outline-none resize-none font-chinese"
            ></textarea>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex justify-end gap-3 mt-6">
          <button on:click={close} class="px-4 py-2 text-sm text-txt-secondary hover:text-txt-primary transition-colors">
            取消
          </button>
          <button
            on:click={submit}
            disabled={submitting || !description.trim()}
            class="px-5 py-2 text-sm rounded bg-cyber-red/80 hover:bg-cyber-red text-white font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "上报中..." : "确认上报"}
          </button>
        </div>
      {/if}
    </div>
  </div>
{/if}
