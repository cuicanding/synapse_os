<script lang="ts">
  import { onMount } from "svelte";
  import MobileWorkbench from "./mobile/MobileWorkbench.svelte";
  import MobileTasks from "./mobile/MobileTasks.svelte";
  import MobileAssets from "./mobile/MobileAssets.svelte";
  import { tasks } from "../lib/stores";
  import { startWs } from "../lib/ws";

  type Tab = "workbench" | "tasks" | "assets";
  let activeTab: Tab = "workbench";

  onMount(async () => {
    // 加载任务数据
    try {
      const res = await fetch("/api/tasks");
      if (res.ok) tasks.set(await res.json());
    } catch (e) { console.error("[mobile] tasks load failed:", e); }
    // 启动 WebSocket 实时更新
    startWs();
  });

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: "workbench", label: "工作台", icon: "💬" },
    { id: "tasks",     label: "任务",   icon: "▤" },
    { id: "assets",    label: "资产",   icon: "📦" },
  ];

  const tabLabels: Record<Tab, string> = {
    workbench: "工作台",
    tasks: "任务",
    assets: "资产",
  };

  function switchToDesktop() {
    localStorage.setItem("synapse_desktop_mode", "1");
    history.replaceState(null, "", "/");
    window.location.reload();
  }
</script>

<div class="mobile-shell">
  <!-- 顶栏 -->
  <header class="mobile-header">
    <span class="mobile-logo">🏠</span>
    <span class="mobile-title">SynapseOS</span>
    <span class="mobile-tab-label">{tabLabels[activeTab]}</span>
    <button class="desktop-btn" on:click={switchToDesktop} title="切换桌面版">🖥</button>
  </header>

  <!-- 内容区 -->
  <main class="mobile-main">
    {#if activeTab === "workbench"}
      <MobileWorkbench />
    {:else if activeTab === "tasks"}
      <MobileTasks />
    {:else if activeTab === "assets"}
      <MobileAssets />
    {/if}
  </main>

  <!-- 底部 Tab 栏 -->
  <nav class="mobile-tabbar">
    {#each tabs as tab}
      <button
        class="tab-item {activeTab === tab.id ? 'active' : ''}"
        on:click={() => { activeTab = tab.id; }}
      >
        <span class="tab-icon">{tab.icon}</span>
        <span class="tab-label">{tab.label}</span>
      </button>
    {/each}
  </nav>
</div>

<style>
  .mobile-shell {
    display: flex;
    flex-direction: column;
    width: 100vw;
    height: 100vh;
    height: 100dvh;
    background: #0A0E1A;
    color: #F0F9FF;
    font-family: "Inter", "Noto Sans SC", sans-serif;
    overflow: hidden;
  }

  /* ─── Header ─────────────────────────────── */
  .mobile-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: rgba(11, 16, 30, 0.95);
    border-bottom: 1px solid rgba(0, 229, 255, 0.12);
    flex-shrink: 0;
    min-height: 50px;
  }

  .mobile-logo {
    font-size: 20px;
    line-height: 1;
  }

  .mobile-title {
    font-size: 15px;
    font-weight: 700;
    color: #00E5FF;
    letter-spacing: 1px;
  }

  .mobile-tab-label {
    flex: 1;
    font-size: 14px;
    color: #94A3B8;
  }

  .desktop-btn {
    background: none;
    border: none;
    font-size: 18px;
    cursor: pointer;
    padding: 4px;
    min-width: 44px;
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    transition: background 0.15s;
  }
  .desktop-btn:active { background: rgba(255,255,255,0.08); }

  /* ─── Main ───────────────────────────────── */
  .mobile-main {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* ─── Tab Bar ────────────────────────────── */
  .mobile-tabbar {
    display: flex;
    align-items: center;
    background: rgba(11, 16, 30, 0.98);
    border-top: 1px solid rgba(0, 229, 255, 0.12);
    flex-shrink: 0;
    /* Safe area for iOS home indicator */
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }

  .tab-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    padding: 10px 0;
    min-height: 56px;
    background: none;
    border: none;
    cursor: pointer;
    transition: all 0.15s;
    color: #475569;
  }

  .tab-item.active {
    color: #00E5FF;
  }

  .tab-icon {
    font-size: 20px;
    line-height: 1;
  }

  .tab-label {
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.3px;
  }

  .tab-item.active .tab-label {
    color: #00E5FF;
    text-shadow: 0 0 8px rgba(0, 229, 255, 0.5);
  }
</style>
