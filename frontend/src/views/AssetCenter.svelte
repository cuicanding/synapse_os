<script lang="ts">
  import { onMount } from "svelte";
  import MarkdownDetail from "../components/MarkdownDetail.svelte";

  // ─── State ──────────────────────────────────────────────────────────────
  let loading = true;
  let grouped: any = { domains: [], missions: [], domains_meta: {} };
  let error = "";

  // Filters
  let filterMission = "";
  let filterDomain = "";
  let filterType = "";
  let filterQ = "";
  let includeArchived = false;

  // Expanded asset
  let expandedId: string | null = null;

  // ─── Fetch ──────────────────────────────────────────────────────────────
  async function fetchAssets() {
    loading = true;
    error = "";
    try {
      // Capture current filter values at call time (avoid closure issues)
      const fDomain = filterDomain;
      const fMission = filterMission;
      const fType = filterType;
      const fQ = filterQ;
      const fArchived = includeArchived;

      const params = new URLSearchParams();
      if (fMission) params.set("mission", fMission);
      if (fDomain) params.set("domain", fDomain);
      if (fType) params.set("type", fType);
      if (fQ) params.set("q", fQ);
      if (fArchived) params.set("include_archived", "true");

      console.log("[AssetCenter] fetching with params:", params.toString());

      const r = await fetch(`/api/assets?${params}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      // Force new object reference so Svelte reactivity fires
      grouped = { ...data };
      console.log("[AssetCenter] got domains:", (grouped.domains || []).map((d: any) => d.id));
    } catch (e: any) {
      error = `加载失败: ${e.message}`;
    } finally {
      loading = false;
    }
  }

  // Debounced search
  let searchTimer: ReturnType<typeof setTimeout>;
  function onQChange() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(fetchAssets, 300);
  }

  // ─── Filter handlers ────────────────────────────────────────────────────
  function setDomain(domain: string) {
    console.log("[AssetCenter] setDomain:", domain);
    filterDomain = domain;
    fetchAssets();
  }
  function setMission(m: string) {
    console.log("[AssetCenter] setMission:", m);
    filterMission = m;
    fetchAssets();
  }
  function setType(t: string) {
    console.log("[AssetCenter] setType:", t);
    filterType = t;
    fetchAssets();
  }
  function toggleArchived() {
    includeArchived = !includeArchived;
    fetchAssets();
  }

  // ─── Domain nav ─────────────────────────────────────────────────────────
  // Flatten domain type counts for nav display
  $: navDomains = (grouped.domains || []).map((d: any) => ({
    id: d.id,
    label: d.label,
    emoji: d.emoji,
    total: d.assets.length,
    typeCounts: d.type_counts,
  }));

  // Assets currently shown (flat list for main area)
  $: displayedAssets = (grouped.domains || []).flatMap((d: any) =>
    d.assets.map((a: any) => ({ ...a, domain: d.id, domainLabel: d.label }))
  );

  // Stats
  $: totalAssets = displayedAssets.length;

  // ─── Helpers ───────────────────────────────────────────────────────────
  const TYPE_OPTIONS = [
    { value: "", label: "全部类型" },
    { value: "MS", label: "📋 里程碑" },
    { value: "FS", label: "⚡ 功能点" },
    { value: "AD", label: "📐 架构决策" },
    { value: "DS", label: "📝 设计方案" },
    { value: "RK", label: "📄 任务记录" },
    { value: "RD", label: "👤 角色定义" },
  ];

  const DOMAIN_LABELS: Record<string, string> = {
    infrastructure: "基础设施域",
    online: "在线业务域",
    offline: "离线业务域",
    growth: "增长域",
    marketing: "市场域",
    quant: "金蟾量化域",
    shared: "共享资产",
  };

  function typeLabel(t: string) {
    return TYPE_OPTIONS.find(o => o.value === t)?.label || t;
  }

  function toggleExpand(id: string) {
    expandedId = expandedId === id ? null : id;
  }

  function formatMtime(ts: number | undefined): string {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "刚刚";
    if (diffMin < 60) return `${diffMin}分钟前`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}小时前`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay}天前`;
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }

  onMount(fetchAssets);
</script>

<div class="page-enter space-y-6">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <div>
      <h1 class="font-orbitron text-2xl font-bold neon-cyan flex items-center gap-2">
        <span>📦</span> 资产中心
      </h1>
      <p class="text-txt-secondary text-sm mt-1 font-chinese">
        组织资产透明化 · {totalAssets} 个资产
      </p>
    </div>
    <button
      on:click={fetchAssets}
      class="glass-card px-3 py-2 text-xs font-mono text-txt-secondary hover:text-cyber-cyan transition-colors"
    >
      ↻ 刷新
    </button>
  </div>

  <!-- ─── Layout: nav sidebar + main area ─────────────────────────────── -->
  <div class="flex gap-6" style="align-items: flex-start;">

    <!-- Left: Domain nav -->
    <div class="w-56 flex-shrink-0 space-y-2">
      <div class="glass-card p-4 space-y-1">
        <p class="text-xs font-mono text-txt-secondary mb-2">域</p>
        <button
          class="w-full text-left px-2 py-1.5 rounded text-xs font-mono transition-colors
            {!filterDomain ? 'bg-cyber-cyan/20 text-cyber-cyan' : 'text-txt-secondary hover:text-txt-primary'}"
          on:click={() => setDomain("")}
        >
          📦 全部
        </button>
        {#each navDomains as d}
          <button
            class="w-full text-left px-2 py-1.5 rounded text-xs font-mono transition-colors
              {filterDomain === d.id ? 'bg-cyber-cyan/20 text-cyber-cyan' : 'text-txt-secondary hover:text-txt-primary'}"
            on:click={() => setDomain(filterDomain === d.id ? "" : d.id)}
          >
            <span class="mr-1">{d.emoji}</span>
            {d.label}
            <span class="float-right opacity-50">({d.total})</span>
          </button>
        {/each}
      </div>

      <!-- Type breakdown per domain (when domain selected) -->
      {#if filterDomain && grouped.domains_meta?.[filterDomain]}
        {@const dm = grouped.domains_meta[filterDomain]}
        <div class="glass-card p-4 space-y-1">
          <p class="text-xs font-mono text-txt-secondary mb-2">类型分布</p>
          {#each Object.entries(dm.type_counts || {}) as [t, cnt]}
            <div class="flex items-center justify-between px-2 py-1">
              <span class="text-xs font-mono text-txt-secondary">{typeLabel(t)}</span>
              <span class="text-xs font-mono text-cyber-cyan">{cnt}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Right: Main area -->
    <div class="flex-1 min-w-0 space-y-4">

      <!-- Filter bar -->
      <div class="glass-card p-4 flex flex-wrap items-center gap-3">
        <!-- Mission -->
        <div class="flex items-center gap-2">
          <span class="text-xs font-mono text-txt-secondary">使命:</span>
          <select bind:value={filterMission}
            on:change={() => setMission(filterMission)}
            class="bg-bg-light/40 border border-white/10 rounded px-2 py-1 text-xs font-mono text-txt-primary focus:border-cyber-cyan/40 focus:outline-none">
            <option value="">全部</option>
            {#each grouped.missions || [] as m}
              <option value={m.id}>{m.title}</option>
            {/each}
          </select>
        </div>

        <!-- Type -->
        <div class="flex items-center gap-2">
          <span class="text-xs font-mono text-txt-secondary">类型:</span>
          <select bind:value={filterType}
            on:change={() => setType(filterType)}
            class="bg-bg-light/40 border border-white/10 rounded px-2 py-1 text-xs font-mono text-txt-primary focus:border-cyber-cyan/40 focus:outline-none">
            {#each TYPE_OPTIONS as opt}
              <option value={opt.value}>{opt.label}</option>
            {/each}
          </select>
        </div>

        <!-- Search -->
        <div class="flex-1 min-w-[200px]">
          <input
            type="text"
            placeholder="搜索资产..."
            bind:value={filterQ}
            on:input={onQChange}
            class="w-full bg-bg-light/40 border border-white/10 rounded px-3 py-1 text-xs font-mono text-txt-primary placeholder-txt-secondary/40 focus:border-cyber-cyan/40 focus:outline-none"
          />
        </div>

        <!-- Include archived -->
        <label class="flex items-center gap-1.5 cursor-pointer select-none">
          <input type="checkbox" bind:checked={includeArchived}
            on:change={toggleArchived}
            class="w-3 h-3 rounded accent-cyber-violet" />
          <span class="text-xs font-mono {includeArchived ? 'text-cyber-violet' : 'text-txt-secondary'}">
            包含历史
          </span>
        </label>
      </div>

      <!-- Error -->
      {#if error}
        <div class="glass-card p-4 border-cyber-red/30 text-cyber-red text-sm">
          {error}
        </div>
      {/if}

      <!-- Loading skeleton -->
      {#if loading}
        <div class="space-y-3">
          {#each Array(4) as _}
            <div class="glass-card p-5 h-24 animate-pulse bg-bg-mid/30"></div>
          {/each}
        </div>

      <!-- Empty state -->
      {:else if displayedAssets.length === 0}
        <div class="glass-card glow-border p-16 text-center space-y-4">
          <div class="text-5xl">📭</div>
          <h2 class="font-rajdhani text-xl font-semibold text-txt-secondary">无匹配资产</h2>
          <p class="text-txt-secondary font-chinese">试试调整筛选条件</p>
        </div>

      <!-- Asset list -->
      {:else}
        <div class="space-y-3">
          {#each displayedAssets as asset (asset.id)}
            {@const isOpen = expandedId === asset.id}
            <div class="glass-card transition-all {isOpen ? 'border-cyber-cyan/30' : 'hover:border-white/10'}">
              <!-- Asset card header -->
              <button class="w-full p-4 text-left" on:click={() => toggleExpand(asset.id)}>
                <div class="flex items-start justify-between gap-3">
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 flex-wrap mb-1.5">
                      <span class="text-xs font-mono text-txt-secondary">
                        {asset.type_emoji} {asset.type_label}
                      </span>
                      <span class="text-xs text-txt-secondary/40">·</span>
                      <span class="text-xs text-cyber-cyan/60">{asset.domainLabel || DOMAIN_LABELS[asset.domain] || asset.domain}</span>
                      {#if asset.archived}
                        <span class="px-1.5 py-0.5 rounded text-xs bg-cyber-violet/10 border border-cyber-violet/20 text-cyber-violet/80">归档</span>
                      {/if}
                      <span class="text-xs text-txt-secondary/40">·</span>
                      <span class="text-xs text-txt-secondary/60">{formatMtime(asset.file_mtime)}</span>
                    </div>
                    <h3 class="font-rajdhani text-base font-semibold leading-tight">{asset.title}</h3>
                    <p class="text-xs text-txt-secondary mt-1 line-clamp-2">{asset.summary || '—'}</p>
                  </div>
                  <span class="text-txt-secondary text-sm transition-transform flex-shrink-0 {isOpen ? 'rotate-90' : ''}">▶</span>
                </div>
              </button>

              <!-- Expanded content -->
              {#if isOpen}
                <div class="px-4 pb-4 pt-0 border-t border-white/5 space-y-3">
                  <!-- Metadata row -->
                  <div class="flex items-center gap-4 text-xs font-mono text-txt-secondary flex-wrap">
                    {#if asset.mission}
                      <span>使命: <span class="text-cyber-cyan">{asset.mission}</span></span>
                    {/if}
                    {#if asset.source_path}
                      <span>来源: <span class="text-txt-secondary/60">{asset.source_path}</span></span>
                    {/if}
                    <span>{asset.word_count || 0} 字</span>
                  </div>

                  <!-- Full content -->
                  {#if asset.content}
                    <MarkdownDetail
                      title="📄 完整内容"
                      content={asset.content}
                      accentColor="cyan"
                      initialOpen={true}
                    />
                  {/if}
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>
</div>
