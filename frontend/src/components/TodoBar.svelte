<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { fetchTodos } from "../lib/api";
  import { startStatusWs, stopStatusWs } from "../lib/status-ws";

  let todos: any[] = [];
  let loading = true;

  async function loadTodos() {
    try {
      const res = await fetchTodos();
      todos = res.todos || [];
    } catch (e) {
      console.error("[TodoBar] fetch failed:", e);
    } finally {
      loading = false;
    }
  }

  function goToPending() {
    window.location.hash = "#/tasks";
    // Dispatch event to trigger filterNeedsGuoba = true
    window.dispatchEvent(new CustomEvent("activate-pending-filter"));
  }

  onMount(async () => {
    await loadTodos();
    const wsUnsubscribe = startStatusWs(() => loadTodos());
    return () => { if (wsUnsubscribe) wsUnsubscribe(); stopStatusWs(); };
  });
</script>

{#if todos.length > 0}
  <button
    class="glass-card p-3 w-full text-left border-cyber-amber/20 hover:border-cyber-amber/40 transition-all cursor-pointer"
    on:click={goToPending}
  >
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <span>📢</span>
        <span class="font-rajdhani text-sm font-bold">待处理</span>
      </div>
      <span class="bg-cyber-amber/20 text-cyber-amber text-xs font-bold px-2 py-0.5 rounded-full">
        {todos.length}
      </span>
    </div>
  </button>
{/if}
