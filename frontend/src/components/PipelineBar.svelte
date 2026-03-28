<script lang="ts">
  import type { PhaseInfo } from "../lib/api";

  export let phases: Record<string, PhaseInfo> = {};
  export let currentPhase: string = "";
  export let currentStatus: string = "";
  export let selectedPhase: string = "";

  const PHASE_ORDER = ["init", "design", "plan", "dev", "test", "done"];

  $: phaseList = PHASE_ORDER.map(id => phases[id] || { id, label: id, status: "pending" });

  function phaseIcon(status: string): string {
    if (status === "approved") return "✅";
    if (status === "auto-approved") return "✅";
    if (status === "in-progress" || status === "pending-review" || status === "discussing") return "🔵";
    if (status === "rejected") return "⚠️";
    if (status === "terminated") return "❌";
    return "⬜";
  }

  function statusText(status: string): string {
    const map: Record<string, string> = {
      pending: "未开始", "in-progress": "进行中", "pending-review": "待评审",
      discussing: "讨论中", approved: "已批准", "auto-approved": "自动批准", rejected: "已驳回", terminated: "已终止",
    };
    return map[status] || status;
  }

  function isActive(id: string): boolean {
    return id === currentPhase;
  }

  function isSelected(id: string): boolean {
    return id === selectedPhase;
  }
</script>

<div class="pipeline-container">
  <div class="pipeline">
    {#each phaseList as phase, i}
      <button
        class="phase-node {phase.status === 'approved' || phase.status === 'auto-approved' ? 'done' : ''} {phase.status === 'auto-approved' ? 'auto-approved' : ''} {isActive(phase.id) ? 'active' : ''} {isSelected(phase.id) ? 'selected' : ''}"
        on:click={() => selectedPhase = phase.id}
        title="{phase.label}: {statusText(phase.status)}"
      >
        <div class="phase-icon">{phaseIcon(phase.status)}</div>
        <div class="phase-label">{phase.label}</div>
        <div class="phase-status">{statusText(phase.status)}</div>
      </button>
      {#if i < phaseList.length - 1}
        <div class="phase-connector" class:completed={phase.status === 'approved' || phase.status === 'auto-approved'}></div>
      {/if}
    {/each}
  </div>
</div>

<style>
  .pipeline-container {
    overflow-x: auto;
    padding: 1rem 0;
  }
  .pipeline {
    display: flex;
    align-items: center;
    gap: 0;
    min-width: fit-content;
  }
  .phase-node {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.1);
    background: rgba(255,255,255,0.03);
    cursor: pointer;
    transition: all 0.2s;
    min-width: 70px;
  }
  .phase-node:hover {
    border-color: rgba(0, 229, 255, 0.3);
    background: rgba(0, 229, 255, 0.05);
  }
  .phase-node.active {
    border-color: rgba(0, 229, 255, 0.5);
    background: rgba(0, 229, 255, 0.1);
    box-shadow: 0 0 12px rgba(0, 229, 255, 0.15);
  }
  .phase-node.selected {
    border-color: rgba(168, 85, 247, 0.5);
    background: rgba(168, 85, 247, 0.1);
  }
  .phase-node.done {
    opacity: 0.7;
  }
  .phase-node.auto-approved {
    border-color: rgba(34, 197, 94, 0.4);
    background: rgba(34, 197, 94, 0.08);
  }
  .phase-icon {
    font-size: 1.2rem;
  }
  .phase-label {
    font-size: 0.7rem;
    font-family: var(--font-chinese);
    color: #e0e0e0;
    white-space: nowrap;
  }
  .phase-status {
    font-size: 0.6rem;
    font-family: var(--font-mono);
    color: #888;
    white-space: nowrap;
  }
  .phase-connector {
    width: 24px;
    height: 2px;
    background: rgba(255,255,255,0.1);
    flex-shrink: 0;
  }
  .phase-connector.completed {
    background: rgba(0, 229, 255, 0.4);
  }
</style>
