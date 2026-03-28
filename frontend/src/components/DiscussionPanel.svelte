<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { phaseDiscuss } from "../lib/api";

  const dispatch = createEventDispatcher();

  export let taskId: string = "";
  export let phaseId: string = "";
  export let phaseLabel: string = "";
  export let phaseStatus: string = "";
  export let discussions: { time: string; sender: string; message: string }[] = [];

  let message = "";
  let loading = false;
  let sender = "guoba";

  async function sendMessage(action: string) {
    if (!message.trim() && action !== "pause_discussion") return;
    loading = true;
    try {
      const res = await phaseDiscuss(taskId, action, message.trim(), sender);
      if (res.success) {
        message = "";
        dispatch("updated", res);
      }
    } finally {
      loading = false;
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage("send_message");
    }
  }

  let showDiscuss = phaseStatus === "discussing" || phaseStatus === "pending-review";
  let hasDiscussions = (discussions || []).length > 0;
  let showPanel = showDiscuss || hasDiscussions;
</script>

<div class="discussion-panel">
  <div class="panel-header">
    <h3>💬 {phaseLabel}</h3>
    <span class="status-tag">
      {#if phaseStatus === "discussing"}🔵 discussing
      {:else if phaseStatus === "pending-review"}🟡 pending-review
      {:else}⚪{/if}
    </span>
  </div>

  <div class="messages">
    {#if !discussions || discussions.length === 0}
      <div class="empty-state">No messages yet</div>
    {:else}
      {#each discussions as msg}
        <div class="message" class:owner={msg.sender === "guoba"}>
          <div class="msg-header">
            <span class="sender">{msg.sender}</span>
            <span class="time">{msg.time}</span>
          </div>
          <div class="msg-content">{msg.message}</div>
        </div>
      {/each}
    {/if}
  </div>

  {#if showPanel}
    <div class="actions">
      <div class="sender-select">
        <label>Sender:</label>
        <select bind:value={sender}>
          <option value="guoba">guoba</option>
          <option value="reed">reed</option>
          <option value="susan">susan</option>
        </select>
      </div>
      <div class="input-row">
        <textarea
          bind:value={message}
          placeholder="Type message..."
          rows="2"
          on:keydown={handleKeydown}
          disabled={loading}
        ></textarea>
      </div>
      <div class="btn-row">
        <button class="btn btn-send" on:click={() => sendMessage("send_message")} disabled={loading || !message.trim()}>
          Send
        </button>
        {#if sender === "guoba"}
          {#if phaseStatus === "pending-review"}
            <button class="btn btn-discuss" on:click={() => sendMessage("start_discussion")} disabled={loading}>
              Start Discussion
            </button>
          {/if}
          {#if phaseStatus === "discussing"}
            <button class="btn btn-approve" on:click={() => sendMessage("approve")} disabled={loading}>
              Approve
            </button>
            <button class="btn btn-reject" on:click={() => sendMessage("reject")} disabled={loading}>
              Reject
            </button>
            <button class="btn btn-pause" on:click={() => sendMessage("pause_discussion")} disabled={loading}>
              Pause
            </button>
          {/if}
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .discussion-panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    border-left: 1px solid rgba(255,255,255,0.08);
    background: rgba(0,0,0,0.2);
  }
  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }
  .panel-header h3 {
    font-size: 0.9rem;
    margin: 0;
  }
  .status-tag {
    font-size: 0.7rem;
    font-family: monospace;
  }
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .empty-state {
    text-align: center;
    color: #555;
    font-size: 0.8rem;
    padding: 2rem;
  }
  .message {
    padding: 8px 12px;
    border-radius: 8px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
  }
  .message.owner {
    background: rgba(0, 229, 255, 0.06);
    border-color: rgba(0, 229, 255, 0.15);
  }
  .msg-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 4px;
  }
  .sender {
    font-size: 0.75rem;
    font-weight: 600;
    color: #00e5ff;
  }
  .time {
    font-size: 0.65rem;
    color: #666;
    font-family: monospace;
  }
  .msg-content {
    font-size: 0.8rem;
    line-height: 1.4;
    color: #ccc;
  }
  .actions {
    padding: 12px;
    border-top: 1px solid rgba(255,255,255,0.08);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .sender-select {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.7rem;
    color: #888;
  }
  .sender-select select {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    color: #ddd;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 0.7rem;
  }
  .input-row textarea {
    width: 100%;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 6px;
    color: #ddd;
    padding: 8px;
    font-size: 0.8rem;
    resize: none;
  }
  .input-row textarea:focus {
    outline: none;
    border-color: rgba(0, 229, 255, 0.4);
  }
  .btn-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .btn {
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 0.7rem;
    border: 1px solid rgba(255,255,255,0.15);
    background: rgba(255,255,255,0.05);
    color: #ccc;
    cursor: pointer;
    transition: all 0.2s;
  }
  .btn:hover:not(:disabled) {
    background: rgba(255,255,255,0.1);
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .btn-send {
    background: rgba(0, 229, 255, 0.15);
    border-color: rgba(0, 229, 255, 0.3);
    color: #00e5ff;
  }
  .btn-approve {
    background: rgba(0, 230, 118, 0.15);
    border-color: rgba(0, 230, 118, 0.3);
    color: #00e676;
  }
  .btn-reject {
    background: rgba(255, 82, 82, 0.15);
    border-color: rgba(255, 82, 82, 0.3);
    color: #ff5252;
  }
  .btn-discuss {
    background: rgba(168, 85, 247, 0.15);
    border-color: rgba(168, 85, 247, 0.3);
    color: #a855f7;
  }
  .btn-pause {
    background: rgba(255, 193, 7, 0.15);
    border-color: rgba(255, 193, 7, 0.3);
    color: #ffc107;
  }
</style>
