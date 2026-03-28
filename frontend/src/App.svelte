<script lang="ts">
  import { onMount } from "svelte";
  import { startWs, stopWs, synapseData, wsConnected, lastUpdated } from "./lib/ws";
  import { mission, tasks, decisions, team, missions, loading, showWorkbench, pendingDecisions } from "./lib/stores";
  import Mission from "./views/Mission.svelte";
  import Tasks from "./views/Tasks.svelte";
  import Decisions from "./views/Decisions.svelte";
  import Team from "./views/Team.svelte";
  import WorkbenchPanel from "./views/WorkbenchPanel.svelte";
  import LoginPage from "./views/LoginPage.svelte";
  import MobileApp from "./views/MobileApp.svelte";

  // ─── Auth ────────────────────────────────────────────────────────────
  let authEnabled = false;
  let loggedIn = false;
  let authChecked = false;

  async function checkAuth() {
    try {
      const r = await fetch("/api/auth");
      const data = await r.json();
      authEnabled = data.enabled;
      if (!authEnabled) {
        loggedIn = true;
      } else {
        const probe = await fetch("/api/missions");
        loggedIn = probe.status !== 401;
      }
    } catch {
      loggedIn = false;
    } finally {
      authChecked = true;
    }
  }

  function handleUnauthorized() {
    loggedIn = false;
  }

  function handleLogin() {
    loggedIn = true;
  }

  // ─── Route ───────────────────────────────────────────────────────────
  let isMobileRoute = false;

  function detectRoute() {
    const path = window.location.pathname;
    if (path === "/mobile") {
      isMobileRoute = true;
      return;
    }
    if (window.innerWidth < 768) {
      const opted = localStorage.getItem("synapse_desktop_mode");
      if (!opted) {
        history.replaceState(null, "", "/mobile");
        isMobileRoute = true;
        return;
      }
    }
    isMobileRoute = false;
  }

  // ─── Hash Router (desktop) ───────────────────────────────────────────
  let hash = location.hash || "#/";
  let currentTab = getTab(hash);

  function getTab(h: string): string {
    if (h === "#/" || h === "#" || h === "") return "mission";
    if (h.startsWith("#/mission/")) return "mission-detail";
    if (h.startsWith("#/tasks")) return "tasks";
    if (h.startsWith("#/decisions")) return "decisions";
    if (h.startsWith("#/team")) return "team";
    return "mission";
  }

  function handleHashChange() {
    hash = location.hash || "#/";
    currentTab = getTab(hash);
  }

  // ─── Particle canvas ─────────────────────────────────────────────────
  let canvas: HTMLCanvasElement;
  let animFrame: number;

  function initParticles() {
    const ctx = canvas.getContext("2d")!;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    interface Particle {
      x: number; y: number;
      vx: number; vy: number;
      size: number; color: string; alpha: number;
    }

    const particles: Particle[] = [];
    const colors = ["#00E5FF", "#7C3AED", "#00E5FF", "#7C3AED"];
    for (let i = 0; i < 60; i++) {
      particles.push({
        x: Math.random() * canvas.width, y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.4,
        size: Math.random() * 2 + 0.5,
        color: colors[Math.floor(Math.random() * colors.length)],
        alpha: Math.random() * 0.5 + 0.1,
      });
    }

    let mouseX = canvas.width / 2;
    let mouseY = canvas.height / 2;
    window.addEventListener("mousemove", (e) => { mouseX = e.clientX; mouseY = e.clientY; });

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const p of particles) {
        const dx = mouseX - p.x; const dy = mouseY - p.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) { p.vx += dx * 0.00005; p.vy += dy * 0.00005; }
        p.x += p.vx; p.y += p.vy; p.vx *= 0.99; p.vy *= 0.99;
        if (p.x < 0) p.x = canvas.width; if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height; if (p.y > canvas.height) p.y = 0;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = p.color; ctx.globalAlpha = p.alpha; ctx.fill(); ctx.globalAlpha = 1;
      }
      animFrame = requestAnimationFrame(draw);
    }
    draw();

    const ro = new ResizeObserver(() => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; });
    ro.observe(document.body);
    return () => { ro.disconnect(); cancelAnimationFrame(animFrame); };
  }

  onMount(async () => {
    detectRoute();
    window.addEventListener("hashchange", handleHashChange);
    window.addEventListener("synapse-unauthorized", handleUnauthorized);

    await checkAuth();

    let cleanup: (() => void) | undefined;
    let unsub: (() => void) | undefined;

    if (loggedIn && !isMobileRoute) {
      startWs();
      cleanup = initParticles();
      unsub = synapseData.subscribe((data) => {
        if (data) {
          mission.set(data.mission as any);
          missions.set((data.missions || []) as any[]);
          tasks.set(data.tasks as any[]);
          decisions.set(data.decisions as any[]);
          team.set(data.team as any[]);
          loading.set(false);
        }
      });
    }

    return () => {
      window.removeEventListener("hashchange", handleHashChange);
      window.removeEventListener("synapse-unauthorized", handleUnauthorized);
      if (unsub) unsub();
      stopWs();
      if (cleanup) cleanup();
    };
  });

  function formatTime(iso: string | null): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
</script>

{#if !authChecked}
  <div style="background:#0A0E1A;width:100vw;height:100vh;"></div>
{:else if !loggedIn}
  <LoginPage on:login={handleLogin} />
{:else if isMobileRoute}
  <MobileApp />
{:else}
  <canvas bind:this={canvas} id="particle-canvas"></canvas>
  <div class="scanline"></div>

  <div class="relative z-10 h-screen cyber-grid flex flex-col overflow-hidden">
    <header class="sticky top-0 z-50 bg-bg-deep/80 backdrop-blur-md border-b border-cyber-cyan/10">
      <div class="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-cyber-cyan to-cyber-violet flex items-center justify-center shadow-cyan">
            <span class="font-orbitron text-xs font-bold text-bg-deep">S2</span>
          </div>
          <h1 class="font-orbitron text-sm font-bold tracking-widest neon-cyan">
            SYNAPSE<span class="text-txt-secondary font-normal">OS 2.0</span>
          </h1>
        </div>

        <nav class="flex items-center gap-1">
          <a href="#/" class="nav-link {currentTab === 'mission' || currentTab === 'mission-detail' ? 'active' : ''}">
            <span class="mr-1">◎</span>使命
          </a>
          <a href="#/tasks" class="nav-link {currentTab === 'tasks' ? 'active' : ''}">
            <span class="mr-1">▤</span>任务
          </a>
          <a href="#/decisions" class="nav-link {currentTab === 'decisions' ? 'active' : ''}">
            <span class="mr-1">◈</span>待决策
          </a>
          <a href="#/team" class="nav-link {currentTab === 'team' ? 'active' : ''}">
            <span class="mr-1">⬟</span>团队
          </a>
        </nav>

        <button
          id="workbench-trigger"
          class="workbench-trigger"
          on:click={() => showWorkbench.update((v) => !v)}
        >
          👑 果爸工作台
          {#if $pendingDecisions.length > 0}
            <span class="workbench-badge">{$pendingDecisions.length}</span>
          {/if}
        </button>

        <div class="flex items-center gap-4 text-xs font-mono">
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full {$wsConnected ? 'bg-cyber-green pulse-glow' : 'bg-cyber-red'}"></span>
            <span class="text-txt-secondary">{$wsConnected ? "LIVE" : "OFFLINE"}</span>
          </div>
          {#if $lastUpdated}
            <span class="text-txt-secondary">↑ {formatTime($lastUpdated)}</span>
          {/if}
        </div>
      </div>
    </header>

    <div class="flex flex-1 overflow-hidden">
      <main class="flex-1 max-w-[1700px] mx-auto px-6 py-8 overflow-y-auto">
        {#if currentTab === "mission" || currentTab === "mission-detail"}
          <Mission />
        {:else if currentTab === "tasks"}
          <Tasks />
        {:else if currentTab === "decisions"}
          <Decisions />
        {:else if currentTab === "team"}
          <Team />
        {:else}
          <Mission />
        {/if}
      </main>

      {#if $showWorkbench}
        <div style="width:960px;flex-shrink:0;border-left:1px solid rgba(0,229,255,0.15);background:rgba(11,16,30,0.98);overflow:hidden;">
          <WorkbenchPanel />
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .scanline {
    position: fixed; top: 0; left: 0; width: 100%; height: 2px;
    background: linear-gradient(90deg, transparent, rgba(0,229,255,0.15), transparent);
    animation: scan 8s linear infinite; pointer-events: none; z-index: 9999;
  }
  @keyframes scan {
    0% { top: 0; opacity: 0; } 5% { opacity: 1; }
    95% { opacity: 1; } 100% { top: 100vh; opacity: 0; }
  }
  .workbench-trigger {
    display: flex; align-items: center; gap: 8px; padding: 8px 14px;
    background: rgba(17, 24, 39, 0.6); backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px); border: 1px solid rgba(0, 229, 255, 0.2);
    border-radius: 8px; color: var(--cyber-cyan); font-family: 'Rajdhani', sans-serif;
    font-weight: 600; font-size: 0.875rem; cursor: pointer; transition: all 0.2s ease;
    text-shadow: 0 0 8px rgba(0, 229, 255, 0.4);
  }
  .workbench-trigger:hover {
    border-color: rgba(0, 229, 255, 0.5); background: rgba(0, 229, 255, 0.08);
    text-shadow: 0 0 12px rgba(0, 229, 255, 0.8); box-shadow: 0 0 20px rgba(0, 229, 255, 0.15);
  }
  .workbench-badge {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 18px; height: 18px; padding: 0 5px;
    background: var(--cyber-amber); color: var(--bg-deep);
    font-size: 10px; font-weight: 700; font-family: monospace; border-radius: 9px;
    animation: pulse-glow 2s ease-in-out infinite;
  }
</style>
