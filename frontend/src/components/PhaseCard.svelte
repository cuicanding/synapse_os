<script lang="ts">
  import type { PhaseInfo } from "../lib/api";
  import { phaseStart, phaseSubmit, phaseApprove, phaseReject, phaseResubmit, phaseTerminate } from "../lib/api";

  export let task: any = {};
  export let phase: PhaseInfo | null = null;
  export let isCurrentPhase: boolean = false;

  let loading = false;

  async function doAction(action: () => Promise<any>) {
    loading = true;
    try {
      await action();
      dispatch("updated");
    } finally {
      loading = false;
    }
  }

  function handleReject() {
    const reason = prompt("驳回原因：");
    if (reason !== null) {
      doAction(() => phaseReject(task.id, reason, false));
    }
  }

  function handleTerminate() {
    const reason = prompt("终止原因：");
    if (reason !== null) {
      doAction(() => phaseTerminate(task.id, reason));
    }
  }
</script>

{#if phase}
  <div class="phase-card">
    <div class="card-header">
      <h3>📋 {phase.label}阶段</h3>
      <span class="phase-status-badge {phase.status === 'auto-approved' ? 'auto-approved-badge' : ''}" class:active={isCurrentPhase}>
        {phase.status === 'approved' ? '✅' : phase.status === 'auto-approved' ? '✅' : phase.status === 'in-progress' ? '🔵' : phase.status === 'pending-review' ? '🟡' : phase.status === 'discussing' ? '💬' : phase.status === 'rejected' ? '⚠️' : '⬜'}
        {phase.status}
      </span>
    </div>

    <div class="card-info">
      <div class="info-row"><span>负责人</span><span>{phase.assignee || '—'}</span></div>
      <div class="info-row"><span>审批人</span><span>果爸</span></div>
      {#if phase.comment}
        <div class="info-row"><span>审批意见</span><span>{phase.comment}</span></div>
      {/if}
    </div>

    <!-- Artifacts -->
    {#if phase.artifacts && phase.artifacts.length > 0}
      <div class="section">
        <h4>📎 产出物</h4>
        <div class="artifacts">
          {#each phase.artifacts as a}
            {#if a.path}
              <a href={a.path} target="_blank" class="artifact-link">📄 {a.name}</a>
            {:else}
              <span class="artifact-link">📄 {a.name}</span>
            {/if}
          {/each}
        </div>
      </div>
    {/if}

    <!-- Action buttons -->
    {#if isCurrentPhase && phase.status !== 'approved' && phase.status !== 'terminated'}
      <div class="section actions">
        <h4>操作</h4>
        <div class="btn-grid">
          {#if phase.status === 'pending'}
            <button class="btn btn-primary" on:click={() => doAction(() => phaseStart(task.id))} disabled={loading}>
              ▶ 开始
            </button>
          {/if}
          {#if phase.status === 'in-progress'}
            <button class="btn btn-primary" on:click={() => doAction(() => phaseSubmit(task.id))} disabled={loading}>
              📤 提交产出物
            </button>
          {/if}
          {#if phase.status === 'rejected'}
            <button class="btn btn-primary" on:click={() => doAction(() => phaseResubmit(task.id))} disabled={loading}>
              🔄 重新开始
            </button>
          {/if}
          <button class="btn btn-danger" on:click={handleTerminate} disabled={loading}>
            🛑 终止任务
          </button>
        </div>
      </div>
    {/if}
  </div>
{/if}

<style>
  .phase-card {
    padding: 1rem;
  }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  .card-header h3 {
    margin: 0;
    font-size: 1rem;
    font-family: var(--font-chinese);
  }
  .phase-status-badge {
    font-size: 0.75rem;
    font-family: var(--font-mono);
    padding: 2px 8px;
    border-radius: 4px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
  }
  .phase-status-badge.active {
    border-color: rgba(0, 229, 255, 0.3);
    background: rgba(0, 229, 255, 0.1);
  }
  .phase-status-badge.auto-approved-badge {
    border-color: rgba(34, 197, 94, 0.4);
    background: rgba(34, 197, 94, 0.1);
    color: #22c55e;
  }
  .card-info {
    margin-bottom: 1rem;
  }
  .info-row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    font-size: 0.8rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
  }
  .info-row span:first-child {
    color: #888;
    font-family: var(--font-chinese);
  }
  .info-row span:last-child {
    color: #ccc;
    font-family: var(--font-chinese);
  }
  .section {
    margin-bottom: 1rem;
  }
  .section h4 {
    font-size: 0.8rem;
    margin-bottom: 0.5rem;
    color: #aaa;
    font-family: var(--font-chinese);
  }
  .artifacts {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .artifact-link {
    font-size: 0.8rem;
    color: #00e5ff;
    text-decoration: none;
    padding: 4px 8px;
    border-radius: 4px;
    background: rgba(0, 229, 255, 0.05);
    border: 1px solid rgba(0, 229, 255, 0.1);
    font-family: var(--font-chinese);
    display: inline-block;
  }
  .btn-grid {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .btn {
    padding: 6px 16px;
    border-radius: 6px;
    font-size: 0.8rem;
    border: 1px solid rgba(255,255,255,0.15);
    background: rgba(255,255,255,0.05);
    color: #ccc;
    cursor: pointer;
    font-family: var(--font-chinese);
    transition: all 0.2s;
  }
  .btn:hover:not(:disabled) {
    background: rgba(255,255,255,0.1);
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .btn-primary {
    background: rgba(0, 229, 255, 0.15);
    border-color: rgba(0, 229, 255, 0.3);
    color: #00e5ff;
  }
  .btn-danger {
    background: rgba(255, 82, 82, 0.1);
    border-color: rgba(255, 82, 82, 0.2);
    color: #ff5252;
  }
</style>
