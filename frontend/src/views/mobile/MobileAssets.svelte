<script lang="ts">
  import { onMount } from "svelte";
  import { fetchFileContent } from "../../lib/api";

  // ─── State ───────────────────────────────────────────────────────────
  let loading = true;
  let grouped: any = { domains: [], missions: [], domains_meta: {} };
  let error = "";
  let filterDomain = "";
  let filterQ = "";
  let searchTimer: ReturnType<typeof setTimeout>;

  // ─── Detail preview ──────────────────────────────────────────────────
  let detailAsset: any | null = null;
  let previewContent = "";
  let previewLoading = false;
  let previewError = "";

  async function fetchAssets() {
    loading = true;
    error = "";
    try {
      const params = new URLSearchParams();
      if (filterDomain) params.set("domain", filterDomain);
      if (filterQ) params.set("q", filterQ);
      const r = await fetch(`/api/assets?${params}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      grouped = { ...data };
    } catch (e: any) {
      error = `加载失败: ${e.message}`;
    } finally {
      loading = false;
    }
  }

  function onQChange() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(fetchAssets, 300);
  }

  function setDomain(domain: string) {
    filterDomain = domain;
    fetchAssets();
  }

  // ─── Flatten all assets ───────────────────────────────────────────────
  $: allAssets = (grouped.domains || []).flatMap((d: any) =>
    (d.assets || []).map((a: any) => ({ ...a, domainId: d.id, domainName: d.name || d.id }))
  );

  $: domains = grouped.domains || [];

  // ─── Relative time ────────────────────────────────────────────────────
  function relTime(dateStr?: string): string {
    if (!dateStr) return "";
    const diff = Date.now() - new Date(dateStr).getTime();
    const d = Math.floor(diff / 86400000);
    if (d === 0) return "今天";
    if (d === 1) return "昨天";
    if (d < 30) return `${d}天前`;
    if (d < 365) return `${Math.floor(d / 30)}个月前`;
    return `${Math.floor(d / 365)}年前`;
  }

  // ─── Open detail ─────────────────────────────────────────────────────
  async function openAsset(asset: any) {
    detailAsset = asset;
    previewContent = "";
    previewError = "";
    if (!asset.path) return;
    previewLoading = true;
    try {
      const res = await fetchFileContent(asset.path);
      previewContent = res.content || "";
      if (!previewContent) previewError = (res as any).error || "无法读取文件";
    } catch (e: any) {
      previewError = e.message || "加载失败";
    } finally {
      previewLoading = false;
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

  onMount(() => { fetchAssets(); });
</script>

<div class="assets-root">
  {#if detailAsset}
    <!-- ─── Asset Detail / Preview ─────────── -->
    <div class="detail-overlay">
      <div class="detail-header">
        <button class="back-btn" on:click={() => { detailAsset = null; previewContent = ""; }}>←</button>
        <span class="detail-title">{detailAsset.title || detailAsset.name || "资产详情"}</span>
      </div>

      <!-- 元信息 -->
      <div class="asset-meta-bar">
        {#if detailAsset.domainName}
          <span class="domain-tag">{detailAsset.domainName}</span>
        {/if}
        {#if detailAsset.type}
          <span class="type-tag">{detailAsset.type}</span>
        {/if}
        {#if detailAsset.updated_at}
          <span class="time-tag">{relTime(detailAsset.updated_at)}</span>
        {/if}
      </div>

      <div class="detail-body">
        {#if previewLoading}
          <div class="center-tip">加载中...</div>
        {:else if previewError}
          <div class="center-tip err">{previewError}</div>
        {:else if previewContent}
          <div class="md-content">{@html parseMarkdown(previewContent)}</div>
        {:else if detailAsset.description}
          <div class="md-content">{@html parseMarkdown(detailAsset.description)}</div>
        {:else}
          <div class="center-tip">暂无内容</div>
        {/if}
      </div>
    </div>

  {:else}
    <!-- ─── Asset List ─────────────────────── -->
    <!-- 搜索框 -->
    <div class="search-bar">
      <input
        type="search"
        bind:value={filterQ}
        on:input={onQChange}
        placeholder="搜索资产..."
        class="search-input"
        style="font-size:16px;"
      />
    </div>

    <!-- 域筛选（横向滚动） -->
    <div class="domain-filter">
      <button class="domain-btn {filterDomain === '' ? 'active' : ''}" on:click={() => setDomain('')}>
        全部
      </button>
      {#each domains as domain}
        <button
          class="domain-btn {filterDomain === domain.id ? 'active' : ''}"
          on:click={() => setDomain(domain.id)}
        >
          {domain.name || domain.id}
        </button>
      {/each}
    </div>

    <div class="asset-list">
      {#if loading}
        <div class="center-tip">加载中...</div>
      {:else if error}
        <div class="center-tip err">{error}</div>
      {:else if allAssets.length === 0}
        <div class="center-tip">暂无资产</div>
      {:else}
        {#each allAssets as asset}
          <button class="asset-card" on:click={() => openAsset(asset)}>
            <div class="asset-card-top">
              <span class="domain-label">{asset.domainName}</span>
              {#if asset.type}
                <span class="type-label">{asset.type}</span>
              {/if}
              <span class="time-label">{relTime(asset.updated_at)}</span>
            </div>
            <div class="asset-title">{asset.title || asset.name || asset.path || "未命名"}</div>
            {#if asset.description}
              <div class="asset-desc">{(asset.description || "").slice(0, 60)}{(asset.description || "").length > 60 ? "…" : ""}</div>
            {/if}
          </button>
        {/each}
      {/if}
    </div>
  {/if}
</div>

<style>
  .assets-root {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    background: #0B101E;
    overflow: hidden;
    position: relative;
  }

  /* ─── Search ─────────────────────────────── */
  .search-bar {
    padding: 10px 14px 6px;
    flex-shrink: 0;
  }

  .search-input {
    width: 100%;
    background: rgba(30,41,59,0.7);
    border: 1px solid rgba(0,229,255,0.2);
    border-radius: 10px;
    padding: 10px 14px;
    color: #F0F9FF;
    font-size: 16px;
    outline: none;
    font-family: inherit;
    transition: border-color 0.2s;
  }

  .search-input::placeholder { color: #475569; }
  .search-input:focus { border-color: rgba(0,229,255,0.4); }

  /* ─── Domain Filter ──────────────────────── */
  .domain-filter {
    display: flex;
    gap: 8px;
    padding: 6px 14px 8px;
    overflow-x: auto;
    flex-shrink: 0;
    scrollbar-width: none;
    border-bottom: 1px solid rgba(0,229,255,0.08);
  }

  .domain-filter::-webkit-scrollbar { display: none; }

  .domain-btn {
    flex-shrink: 0;
    padding: 6px 14px;
    border-radius: 20px;
    background: rgba(30,41,59,0.6);
    border: 1px solid rgba(255,255,255,0.1);
    color: #94A3B8;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    min-height: 34px;
    transition: all 0.15s;
    white-space: nowrap;
  }

  .domain-btn.active {
    background: rgba(0,229,255,0.12);
    border-color: rgba(0,229,255,0.4);
    color: #00E5FF;
  }

  /* ─── Asset List ─────────────────────────── */
  .asset-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  }

  .asset-card {
    display: flex;
    flex-direction: column;
    gap: 6px;
    width: 100%;
    padding: 14px 16px;
    background: none;
    border: none;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    cursor: pointer;
    text-align: left;
    color: inherit;
    font-family: inherit;
    transition: background 0.12s;
    min-height: 70px;
  }

  .asset-card:active { background: rgba(255,255,255,0.04); }

  .asset-card-top {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .domain-label {
    font-size: 11px;
    font-weight: 600;
    color: #00E5FF;
    background: rgba(0,229,255,0.1);
    padding: 2px 7px;
    border-radius: 4px;
  }

  .type-label {
    font-size: 11px;
    color: #7C3AED;
    background: rgba(124,58,237,0.1);
    padding: 2px 6px;
    border-radius: 4px;
  }

  .time-label {
    font-size: 11px;
    color: #475569;
    margin-left: auto;
  }

  .asset-title {
    font-size: 15px;
    font-weight: 600;
    color: #E2E8F0;
    line-height: 1.3;
    word-break: break-word;
  }

  .asset-desc {
    font-size: 13px;
    color: #64748B;
    line-height: 1.4;
  }

  /* ─── Detail Overlay ─────────────────────── */
  .detail-overlay {
    position: absolute;
    inset: 0;
    background: #0B101E;
    display: flex;
    flex-direction: column;
    z-index: 10;
    overflow: hidden;
  }

  .detail-header {
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

  .detail-title {
    flex: 1;
    font-size: 15px;
    font-weight: 600;
    color: #E2E8F0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .asset-meta-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    flex-wrap: wrap;
    border-bottom: 1px solid rgba(0,229,255,0.06);
    flex-shrink: 0;
  }

  .domain-tag {
    font-size: 12px;
    color: #00E5FF;
    background: rgba(0,229,255,0.1);
    padding: 3px 9px;
    border-radius: 6px;
  }

  .type-tag {
    font-size: 12px;
    color: #7C3AED;
    background: rgba(124,58,237,0.1);
    padding: 3px 9px;
    border-radius: 6px;
  }

  .time-tag {
    font-size: 12px;
    color: #475569;
  }

  .detail-body {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

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
