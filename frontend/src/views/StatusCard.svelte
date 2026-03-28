<script lang="ts">
  import type { AgentStatus } from "../lib/api";

  export let agent: AgentStatus;
  export let onHistory: (agentId: string) => void;
  export let onDifficulty: (agentId: string) => void;

  const progressLabels: Record<string, string> = {
    planning: "📋 规划中",
    developing: "🔨 开发中",
    testing: "🧪 测试中",
    deploying: "🚀 部署中",
    completed: "✅ 已完成",
    idle: "☕ 空闲",
  };

  const difficultyLabels: Record<string, { icon: string; text: string }> = {
    none: { icon: "✅", text: "暂无阻塞" },
    minor: { icon: "⚡", text: "小困难" },
    blocking: { icon: "🚨", text: "阻塞中" },
  };

  const initials = (name: string) => {
    const parts = name.replace(/[^\u4e00-\u9fa5a-zA-Z]/g, "").split("");
    return parts.length >= 2 ? parts.slice(0, 2).join("") : parts[0]?.toUpperCase() || "?";
  };

  const avatarColors: Record<string, string> = {
    susan: "from-cyber-violet to-cyber-pink",
    reed: "from-cyber-cyan to-cyber-blue",
    guoba: "from-cyber-amber to-cyber-red",
  };

  function getBorderColor(): string {
    if (agent.difficulty_level === "blocking") return "border-cyber-red";
    if (agent.needs_decision) return "border-cyber-amber";
    if (agent.is_stale) return "border-cyber-amber/40";
    if (agent.progress === "idle") return "border-txt-secondary/20";
    return "border-cyber-cyan/20";
  }

  function getBorderGlow(): string {
    if (agent.difficulty_level === "blocking") return "shadow-red pulse-shadow";
    if (agent.needs_decision) return "shadow-amber";
    return "";
  }

  function timeAgo(iso: string): string {
    if (!iso) return "—";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "刚刚";
    if (mins < 60) return `${mins}分钟前`;
    const hours = Math.floor(mins / 60);
    return `${hours}小时前`;
  }

  $: borderColor = getBorderColor();
  $: borderGlow = getBorderGlow();
  $: diffInfo = difficultyLabels[agent.difficulty_level] || difficultyLabels.none;
  $: avatarGrad = avatarColors[agent.agent_id] || "from-cyber-cyan to-cyber-violet";
</script>

<div class="glass-card p-5 border-2 {borderColor} {borderGlow} hover:scale-[1.01] transition-all relative group">
  <!-- Stale warning overlay -->
  {#if agent.is_stale}
    <div class="absolute top-3 right-3">
      <span class="bg-cyber-amber/20 text-cyber-amber text-xs font-mono px-2 py-0.5 rounded-full flex items-center gap-1">
        ⚠️ 超时
      </span>
    </div>
  {/if}

  <!-- Header: Avatar + Name -->
  <div class="flex items-center gap-3">
    <div class="relative flex-shrink-0">
      <div class="w-11 h-11 rounded-xl bg-gradient-to-br {avatarGrad} p-0.5">
        <div class="w-full h-full rounded-[10px] bg-bg-mid flex items-center justify-center">
          <span class="font-orbitron text-sm font-bold text-txt-primary">
            {initials(agent.agent_name)}
          </span>
        </div>
      </div>
      {#if !agent.is_stale}
        <span class="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-cyber-green border-2 border-bg-mid pulse-glow"></span>
      {:else}
        <span class="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-cyber-amber border-2 border-bg-mid"></span>
      {/if}
    </div>
    <div class="flex-1 min-w-0">
      <h3 class="font-rajdhani text-base font-bold text-txt-primary truncate">
        {agent.agent_name}
      </h3>
      <p class="text-xs text-txt-secondary font-mono">
        {agent.role}{agent.domain ? ` · ${agent.domain}` : ""}
      </p>
    </div>
  </div>

  <!-- Current Task -->
  <div class="mt-3 pt-3 border-t border-white/5">
    <p class="text-xs font-mono text-txt-secondary mb-1">当前任务</p>
    <p class="text-sm font-chinese text-txt-primary font-medium truncate" title={agent.current_task}>
      {agent.current_task || "—"}
    </p>
  </div>

  <!-- Progress -->
  <div class="mt-2">
    <div class="flex items-center justify-between">
      <p class="text-xs font-mono text-txt-secondary">进展</p>
      <span class="text-xs">{progressLabels[agent.progress] || agent.progress}</span>
    </div>
    {#if agent.progress_detail}
      <p class="text-xs font-chinese text-txt-secondary/80 mt-1">{agent.progress_detail}</p>
    {/if}
  </div>

  <!-- Difficulty & Decision -->
  <div class="mt-3 grid grid-cols-2 gap-2">
    <div class="rounded-lg {agent.difficulty_level === 'blocking' ? 'bg-cyber-red/10 border border-cyber-red/20' : 'bg-white/3'} p-2">
      <p class="text-xs font-mono text-txt-secondary">困难</p>
      <p class="text-xs mt-0.5 {agent.difficulty_level === 'blocking' ? 'text-cyber-red' : 'text-txt-secondary'}">
        {diffInfo.icon} {agent.difficulty || diffInfo.text}
      </p>
    </div>
    <div class="rounded-lg {agent.needs_decision ? 'bg-cyber-amber/10 border border-cyber-amber/20' : 'bg-white/3'} p-2">
      <p class="text-xs font-mono text-txt-secondary">待决策</p>
      <p class="text-xs mt-0.5 {agent.needs_decision ? 'text-cyber-amber' : 'text-txt-secondary'}">
        {agent.needs_decision ? "🔔 需要" : "✅ 无需"}
      </p>
    </div>
  </div>

  <!-- Decision detail -->
  {#if agent.needs_decision}
    <div class="mt-2 p-2 rounded bg-cyber-amber/5 border border-cyber-amber/10">
      <p class="text-xs font-chinese text-cyber-amber/90">{agent.needs_decision}</p>
    </div>
  {/if}

  <!-- Difficulty detail -->
  {#if agent.difficulty && agent.difficulty_level !== "none"}
    <div class="mt-2 p-2 rounded bg-cyber-red/5 border border-cyber-red/10">
      <p class="text-xs font-chinese text-cyber-red/90">{agent.difficulty}</p>
    </div>
  {/if}

  <!-- Footer -->
  <div class="mt-3 pt-3 border-t border-white/5 flex items-center justify-between">
    <span class="text-xs font-mono text-txt-secondary">
      📡 {timeAgo(agent.last_report_at)}
    </span>
    <div class="flex gap-1.5">
      <button
        on:click={() => onHistory(agent.agent_id)}
        class="text-xs px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-txt-secondary hover:text-txt-primary transition-colors"
      >
        📋 历史
      </button>
      <button
        on:click={() => onDifficulty(agent.agent_id)}
        class="text-xs px-2 py-1 rounded bg-white/5 hover:bg-cyber-red/10 text-txt-secondary hover:text-cyber-red transition-colors"
      >
        🚨 困难
      </button>
    </div>
  </div>
</div>
