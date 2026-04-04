<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { writable, derived, get } from "svelte/store";

  // ─── Types ───────────────────────────────────────────────────────────
  interface Turn {
    role: string;
    type: "user" | "turn";
    content?: string;
    response?: string;
    thinking?: string;
    streaming?: boolean;
    waitingForFirstDelta?: boolean;
    senderId?: string;
    senderName?: string;
    timestamp?: string;
  }

  interface Channel {
    id: string;
    name: string;
    icon: string;
    type: "domain" | "dm";
  }

  interface ChannelState {
    messages: Turn[];
    isStreaming: boolean;
    unreadCount: number;
  }

  // ─── View state ──────────────────────────────────────────────────────
  let view: "list" | "chat" = "list";
  let listTab: "channels" | "dm" = "dm";

  // ─── WS state ────────────────────────────────────────────────────────
  let ws: WebSocket | null = null;
  let wsStatus: "disconnected" | "connecting" | "connected" = "disconnected";
  let channels: Channel[] = [];
  const currentChannelStore = writable("");
  let currentChannelId = "";
  currentChannelStore.subscribe(v => { currentChannelId = v; });
  let joinedChannels: Set<string> = new Set();

  // ─── Svelte Store for channel states (guaranteed reactivity) ────────
  const DEFAULT_STATE: ChannelState = { messages: [], isStreaming: false, unreadCount: 0 };
  const channelStatesStore = writable<Record<string, ChannelState>>({});

  function updateChannelState(channelId: string, updater: (prev: ChannelState) => ChannelState) {
    channelStatesStore.update(all => {
      const prev = all[channelId] || DEFAULT_STATE;
      return { ...all, [channelId]: updater(prev) };
    });
  }

  // Derived stores for current channel (now depends on currentChannelStore too)
  const currentMessages = derived(
    [channelStatesStore, currentChannelStore],
    ([$cs, $ch]) => ($cs[$ch] || DEFAULT_STATE).messages
  );
  const currentIsStreaming = derived(
    [channelStatesStore, currentChannelStore],
    ([$cs, $ch]) => ($cs[$ch] || DEFAULT_STATE).isStreaming
  );

  const AGENT_PROFILES: Record<string, { name: string; emoji: string; color: string; role: string }> = {
    main:        { name: "果爸",   emoji: "👑", color: "#FFB800", role: "董事长" },
    susan:       { name: "苏珊",   emoji: "🎨", color: "#7C3AED", role: "主设计师" },
    reed:        { name: "里德",   emoji: "🔧", color: "#00E5FF", role: "架构师" },
    zhouhuajian: { name: "周华健", emoji: "📊", color: "#06b6d4", role: "策略分析师" },
    renxianqi:   { name: "任贤齐", emoji: "💻", color: "#8b5cf6", role: "策略开发师" },
    aniu:        { name: "阿牛",   emoji: "💻", color: "#8b5cf6", role: "策略开发师" },
    zhouxingchi: { name: "周星驰", emoji: "🗄️", color: "#10b981", role: "数据工程师" },
  };

  // 从 channels 推导 DM 列表（dm-xxx）
  $: dmChannels = channels.filter(c => c.type === "dm");
  $: domainChannels = channels.filter(c => c.type === "domain");

  function getState(id: string): ChannelState {
    return get(channelStatesStore)[id] || DEFAULT_STATE;
  }

  // ─── Chat scroll ─────────────────────────────────────────────────────
  let chatScrollEl: HTMLDivElement;
  let userScrolledAway = false;
  let newMsgCount = 0;

  function isAtBottom() {
    if (!chatScrollEl) return true;
    return chatScrollEl.scrollHeight - chatScrollEl.scrollTop - chatScrollEl.clientHeight < 80;
  }
  function scrollToBottom() {
    if (!chatScrollEl) return;
    chatScrollEl.scrollTo({ top: chatScrollEl.scrollHeight, behavior: "smooth" });
  }
  function handleScroll() {
    if (isAtBottom()) { userScrolledAway = false; newMsgCount = 0; }
    else { userScrolledAway = true; }
  }
  function triggerSmartScroll() {
    if (!userScrolledAway) { setTimeout(() => scrollToBottom(), 30); }
    else { newMsgCount++; }
  }

  // ─── On-screen debug log ─────────────────────────────────────────────
  // ─── WS Connection ───────────────────────────────────────────────────
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempts = 0;

  function scheduleReconnect() {
    if (reconnectTimer) return;
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
    reconnectAttempts++;
    reconnectTimer = setTimeout(() => { reconnectTimer = null; connectWs(); }, delay);
  }

  function connectWs() {
    if (ws && ws.readyState === WebSocket.OPEN) return;
    wsStatus = "connecting";
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${window.location.hostname}:${window.location.port}/ws/chat`);

    ws.onopen = () => { wsStatus = "connected"; reconnectAttempts = 0; };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      const mtype = msg.type;

      if (mtype === "channel_list") {
        channels = msg.channels || [];
        return;
      }

      if (mtype === "channel_joined") {
        const channelId = msg.channelId;
        const history = msg.history || [];
        const mapped: Turn[] = history.map((m: any) => {
          const isUser = m.role === "user" || m.senderId === "user";
          return {
            role: isUser ? "user" : "assistant",
            type: isUser ? "user" : "turn",
            content: isUser ? (m.content || "") : "",
            response: isUser ? "" : (m.content || ""),
            senderId: m.senderId || m.agent || "",
            senderName: m.senderName || AGENT_PROFILES[m.senderId]?.name || "",
            timestamp: m.timestamp,
          };
        });
        currentChannelStore.set(channelId);
        currentChannelId = channelId;
        joinedChannels.add(channelId);

        channelStatesStore.update(all => ({
          ...all,
          [channelId]: { ...(all[channelId] || DEFAULT_STATE), messages: mapped, unreadCount: 0 },
        }));

        setTimeout(() => scrollToBottom(), 200);
        return;
      }

      if (mtype === "channel_message") {
        const chId = msg.channelId;
        updateChannelState(chId, prev => ({
          ...prev,
          messages: [...prev.messages, {
            role: msg.senderId === "user" ? "user" : "assistant",
            type: msg.senderId === "user" ? "user" : "turn",
            content: msg.content,
            senderId: msg.senderId,
            senderName: msg.senderName,
            timestamp: msg.timestamp,
          }],
          unreadCount: chId === currentChannelId ? prev.unreadCount : prev.unreadCount + 1,
        }));
        if (msg.channelId === currentChannelId) triggerSmartScroll();
        return;
      }

      if (mtype === "agent_thinking") {
        const tid = msg.channelId || (msg.agent ? `dm-${msg.agent}` : currentChannelId);
        updateChannelState(tid, prev => {
          const msgs = prev.messages;
          const last = msgs[msgs.length - 1];
          if (last && last.senderId === msg.agent && last.type === "turn" && last.streaming) {
            return prev; // already have placeholder
          }
          return {
            ...prev,
            isStreaming: true,
            messages: [...msgs, {
              role: "assistant", type: "turn", response: "", thinking: "",
              streaming: true, waitingForFirstDelta: true,
              senderId: msg.agent,
              senderName: msg.agentName || AGENT_PROFILES[msg.agent]?.name || msg.agent,
            }],
          };
        });
        if (tid === currentChannelId) triggerSmartScroll();
        return;
      }

      if (mtype === "session_reset") {
        if (msg.success) {
          updateChannelState(msg.channelId, () => ({ ...DEFAULT_STATE, messages: [] }));
        }
        return;
      }

      // Resolve target channel: prefer explicit channelId, then infer from agent, last resort currentChannelId
      function resolveTid(m: any): string {
        if (m.channelId) return m.channelId;
        if (m.agent && AGENT_PROFILES[m.agent]) return `dm-${m.agent}`;
        return currentChannelId;
      }

      if (mtype === "delta") {
        const tid = resolveTid(msg);
        updateChannelState(tid, prev => {
          const msgs = prev.messages;
          const last = msgs[msgs.length - 1];
          let newMsgs: Turn[];
          if (!last || last.type !== "turn") {
            newMsgs = [...msgs, {
              role: "assistant", type: "turn", response: msg.content || "",
              streaming: true, senderId: msg.agent,
              senderName: AGENT_PROFILES[msg.agent]?.name || msg.agent,
            }];
          } else {
            newMsgs = msgs.map((m, i) =>
              i === msgs.length - 1
                ? { ...m, waitingForFirstDelta: false, response: (m.response || "") + msg.content }
                : m
            );
          }
          return { ...prev, messages: newMsgs };
        });
        if (tid === currentChannelId) triggerSmartScroll();
        return;
      }

      if (mtype === "thinking") {
        const tid = resolveTid(msg);
        updateChannelState(tid, prev => {
          const msgs = prev.messages;
          const last = msgs[msgs.length - 1];
          let newMsgs: Turn[];
          if (!last || last.type !== "turn") {
            newMsgs = [...msgs, {
              role: "assistant", type: "turn", response: "", thinking: msg.content,
              streaming: true, senderId: msg.agent,
              senderName: AGENT_PROFILES[msg.agent]?.name || msg.agent,
            }];
          } else {
            newMsgs = msgs.map((m, i) =>
              i === msgs.length - 1
                ? { ...m, waitingForFirstDelta: false, thinking: (m.thinking || "") + msg.content }
                : m
            );
          }
          return { ...prev, messages: newMsgs };
        });
        if (tid === currentChannelId) triggerSmartScroll();
        return;
      }

      if (mtype === "done") {
        const tid = resolveTid(msg);
        updateChannelState(tid, prev => {
          const newMsgs = prev.messages.map((m, i) =>
            i === prev.messages.length - 1 && m.type === "turn" ? { ...m, streaming: false } : m
          );
          return { ...prev, messages: newMsgs, isStreaming: false };
        });
        if (tid === currentChannelId) triggerSmartScroll();
        return;
      }

      if (mtype === "error") {
        const tid = resolveTid(msg);
        updateChannelState(tid, prev => ({
          ...prev,
          isStreaming: false,
          messages: [...prev.messages, { role: "system", type: "user", content: "❌ " + msg.content }],
        }));
        return;
      }
    };

    ws.onclose = (e) => { wsStatus = "disconnected"; scheduleReconnect(); };
    ws.onerror = (e) => { wsStatus = "disconnected"; };
  }

  // ─── Actions ─────────────────────────────────────────────────────────
  function joinChannel(channelId: string) {
    if (channelId === currentChannelId && view === "chat") return;
    currentChannelStore.set(channelId);
    currentChannelId = channelId;
    userScrolledAway = false;
    newMsgCount = 0;
    view = "chat";

    if (!joinedChannels.has(channelId)) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "join_channel", channelId }));
      }
    } else {
      updateChannelState(channelId, prev => ({ ...prev, unreadCount: 0 }));
      setTimeout(scrollToBottom, 100);
    }
  }

  let chatMessage = "";
  let chatMessageRaw = "";

  function sendMessage() {
    const text = (chatMessage || chatMessageRaw).trim();
    if (!text || wsStatus !== "connected" || !currentChannelId) return;
    chatMessage = "";
    chatMessageRaw = "";
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "send_message", channelId: currentChannelId, message: text }));
    }
    updateChannelState(currentChannelId, prev => ({
      ...prev,
      messages: [...prev.messages, { role: "user", type: "user", content: text, senderId: "user", senderName: "你" }],
    }));
    if (!userScrolledAway) setTimeout(scrollToBottom, 100);
  }

  function handleInputKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && e.ctrlKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  // ─── Markdown mini renderer ───────────────────────────────────────────
  function parseMarkdown(text: string): string {
    if (!text) return "";
    // Process tables first (before \n → <br/>)
    text = text.replace(/^(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)*)/gm, function(match, header, sep, body) {
      var headers = header.split('|').filter(c => c.trim()).map(c => '<th style="padding:6px 10px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.05);font-weight:600;text-align:left;font-size:12px;white-space:nowrap;">' + c.trim() + '</th>').join('');
      var rows = body.trim().split('\n').map(function(row) {
        var cells = row.split('|').filter(c => c.trim()).map(c => '<td style="padding:5px 10px;border:1px solid rgba(255,255,255,0.08);font-size:12px;">' + c.trim() + '</td>').join('');
        return '<tr>' + cells + '</tr>';
      }).join('');
      return '<table style="border-collapse:collapse;margin:8px 0;width:100%;max-width:100%;overflow-x:auto;display:block;">' +
        '<thead>' + headers + '</thead><tbody>' + rows + '</tbody></table>';
    });
    return text
      .replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre style="background:rgba(0,0,0,0.4);padding:10px;border-radius:6px;overflow-x:auto;margin:8px 0;font-size:12px;"><code>$2</code></pre>')
      .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#fff;">$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code style="background:rgba(0,0,0,0.3);padding:1px 5px;border-radius:3px;font-family:monospace;font-size:12px;">$1</code>')
      .replace(/^#### (.+)$/gm, '<div style="font-size:14px;font-weight:700;color:#ccc;margin:10px 0 4px;">$1</div>')
      .replace(/^### (.+)$/gm, '<div style="font-size:15px;font-weight:700;color:#fff;margin:12px 0 6px;">$1</div>')
      .replace(/^## (.+)$/gm, '<div style="font-size:16px;font-weight:700;color:#fff;margin:14px 0 8px;">$1</div>')
      .replace(/^# (.+)$/gm, '<div style="font-size:17px;font-weight:700;color:#fff;margin:16px 0 8px;">$1</div>')
      .replace(/^- (.+)$/gm, '<div style="padding-left:12px;margin:2px 0;">• $1</div>')
      .replace(/^\d+\. (.+)$/gm, '<div style="padding-left:12px;margin:2px 0;">$1</div>')
      .replace(/\n/g, '<br/>');
  }

  async function syncFromSession() {
    if (!currentChannelId || !currentChannelId.startsWith("dm-")) return;
    var agentId = currentChannelId.replace("dm-", "");
    try {
      var resp = await fetch("/api/chat/sync-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId })
      });
      if (!resp.ok) return;
      console.log("[mobile] sync OK, rejoining");
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "join_channel", channelId: currentChannelId }));
      }
    } catch (e) {
      console.error("[mobile] sync failed:", e);
    }
  }

  function getChannelLabel(channelId: string): string {
    const ch = channels.find(c => c.id === channelId);
    if (ch) return ch.name;
    if (channelId.startsWith("dm-")) {
      const aid = channelId.slice(3);
      return AGENT_PROFILES[aid]?.name || aid;
    }
    return channelId;
  }

  function getChannelIcon(channelId: string): string {
    const ch = channels.find(c => c.id === channelId);
    if (ch) return ch.icon;
    if (channelId.startsWith("dm-")) {
      const aid = channelId.slice(3);
      return AGENT_PROFILES[aid]?.emoji || "👤";
    }
    return "💬";
  }

  function formatTs(ts?: string): string {
    if (!ts) return "";
    return new Date(ts).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }

  function lastMessage(channelId: string): string {
    const state = getState(channelId);
    if (!state.messages.length) return "暂无消息";
    const last = state.messages[state.messages.length - 1];
    const text = last.content || last.response || "";
    return text.slice(0, 30) + (text.length > 30 ? "…" : "");
  }

  // ─── Activity Pulse（实时动作指示器，30s 轮询）────────────────────────
  interface ActivityPulseEntry {
    action: string;
    elapsed_seconds: number;
  }
  let activityPulses: Record<string, ActivityPulseEntry | null> = {};
  let pulseTimer: ReturnType<typeof setInterval> | null = null;

  async function fetchActivityPulse() {
    try {
      const r = await fetch("/api/activity-pulse");
      if (r.ok) {
        const data = await r.json();
        activityPulses = data.pulses || {};
      }
    } catch (e) {
      // silent
    }
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────
  onMount(() => {
    connectWs();
    fetchActivityPulse();
    pulseTimer = setInterval(fetchActivityPulse, 30000);
    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
  });
  onDestroy(() => {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (pulseTimer) clearInterval(pulseTimer);
  });
</script>

<div class="wb-root">
  {#if view === "list"}
    <!-- ─── 频道列表视图 ─────────────────────────── -->
    <div class="list-view">
      <div class="sub-tabs">
        <button class="sub-tab {listTab === 'channels' ? 'active' : ''}" on:click={() => { listTab = 'channels'; }}>
          频道
        </button>
        <button class="sub-tab {listTab === 'dm' ? 'active' : ''}" on:click={() => { listTab = 'dm'; }}>
          私聊
        </button>
      </div>

      <div class="ws-bar">
        <span class="ws-dot {wsStatus}"></span>
        <span class="ws-text">{wsStatus === 'connected' ? '已连接' : wsStatus === 'connecting' ? '连接中...' : '未连接'}</span>
      </div>

      <div class="channel-list">
        {#if listTab === 'channels'}
          {#each domainChannels as ch}
            <button class="ch-item" on:click={() => joinChannel(ch.id)}>
              <span class="ch-icon">{ch.icon}</span>
              <div class="ch-info">
                <div class="ch-name">{ch.name}</div>
                <div class="ch-preview">{lastMessage(ch.id)}</div>
              </div>
            </button>
          {/each}
          {#if domainChannels.length === 0}
            <div class="empty-tip">加载中...</div>
          {/if}
        {:else}
          {#each Object.entries(AGENT_PROFILES) as [agentId, profile]}
            {@const dmId = `dm-${agentId}`}
            {@const pulse = activityPulses[agentId] || null}
            {@const isStaleAction = pulse ? pulse.elapsed_seconds > 600 : false}
            <button class="ch-item" on:click={() => joinChannel(dmId)}>
              <span class="ch-icon">{profile.emoji}</span>
              <div class="ch-info">
                <div class="ch-name">{profile.name}</div>
                {#if pulse?.action}
                  <div class="ch-preview ch-pulse" class:ch-pulse-stale={isStaleAction}>
                    <span class="pulse-dot" class:pulse-dot-stale={isStaleAction}></span>
                    {pulse.action}
                  </div>
                {:else}
                  <div class="ch-preview ch-role">{profile.role}</div>
                {/if}
              </div>
            </button>
          {/each}
        {/if}
      </div>
    </div>

  {:else}
    <!-- ─── 聊天视图 ─────────────────────────────── -->
    <div class="chat-view">
      <div class="chat-header">
        <button class="back-btn" on:click={() => { view = 'list'; }}>←</button>
        <span class="chat-icon">{getChannelIcon(currentChannelId)}</span>
        <span class="chat-title">{getChannelLabel(currentChannelId)}</span>
        <button class="sync-btn" on:click={syncFromSession} title="同步">⟳</button>
        <span class="ws-dot-small {wsStatus}"></span>
      </div>

      <div
        class="msg-list"
        bind:this={chatScrollEl}
        on:scroll={handleScroll}
      >
        {#if $currentMessages.length === 0}
          <div class="empty-chat">
            <div style="font-size:28px;margin-bottom:8px;">💬</div>
            <div>发送消息开始对话</div>
          </div>
        {/if}

        {#each $currentMessages as item}
          {#if item.type === "user"}
            <div class="bubble-row user-row">
              <div class="bubble user-bubble">
                {item.content || ""}
              </div>
            </div>
          {:else if item.type === "turn"}
            <div class="bubble-row agent-row">
              <div class="agent-avatar" style="background: linear-gradient(135deg,{AGENT_PROFILES[item.senderId || '']?.color || '#7c3aed'}88,{AGENT_PROFILES[item.senderId || '']?.color || '#7c3aed'});">
                {AGENT_PROFILES[item.senderId || ""]?.emoji || "🤖"}
              </div>
              <div class="agent-content">
                <div class="agent-meta">
                  <span class="agent-name" style="color:{AGENT_PROFILES[item.senderId || '']?.color || '#7c3aed'};">
                    {item.senderName || AGENT_PROFILES[item.senderId || ""]?.name || item.senderId}
                  </span>
                  <span class="agent-time">{formatTs(item.timestamp)}</span>
                </div>

                {#if item.waitingForFirstDelta}
                  <div class="thinking-indicator">💭 正在思考...</div>
                {/if}

                {#if item.thinking && item.streaming && !item.response}
                  <div class="thinking-block">
                    <div class="thinking-label">💭 思考中...</div>
                    <div class="thinking-text">{item.thinking}</div>
                  </div>
                {/if}

                {#if item.response || item.streaming}
                  <div class="agent-bubble">
                    {#if item.streaming}
                      <span class="stream-text">{item.response || ""}<span class="cursor">▋</span></span>
                    {:else}
                      {@html parseMarkdown(item.response || "")}
                    {/if}
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        {/each}

        {#if $currentIsStreaming}
          <div class="streaming-indicator">
            <span class="dot-pulse"></span>AI 正在回复中...
          </div>
        {/if}
      </div>

      {#if userScrolledAway && newMsgCount > 0}
        <button class="new-msg-btn" on:click={() => { userScrolledAway = false; newMsgCount = 0; scrollToBottom(); }}>
          ⬇ {newMsgCount} 条新消息
        </button>
      {/if}

      <div class="input-area">
        <textarea
          bind:value={chatMessage}
          on:input={(e) => { chatMessageRaw = e.target.value; }}
          on:keydown={handleInputKeydown}
          placeholder="发送消息... (Ctrl+Enter 发送)"
          rows={2}
          class="msg-input"
          style="font-size:16px;"
        ></textarea>
        <button
          class="send-btn {(!chatMessage.trim() || wsStatus !== 'connected') ? 'disabled' : ''}"
          on:click={sendMessage}
          disabled={!chatMessage.trim() || wsStatus !== "connected"}
        >发送</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .wb-root {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    background: #0B101E;
    overflow: hidden;
  }

  .list-view {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }

  .sub-tabs {
    display: flex;
    border-bottom: 1px solid rgba(0,229,255,0.1);
    flex-shrink: 0;
  }

  .sub-tab {
    flex: 1;
    padding: 12px;
    background: none;
    border: none;
    color: #94A3B8;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.15s;
    min-height: 44px;
  }

  .sub-tab.active {
    color: #00E5FF;
    border-bottom-color: #00E5FF;
  }

  .ws-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 16px;
    font-size: 12px;
    color: #475569;
    border-bottom: 1px solid rgba(0,229,255,0.06);
    flex-shrink: 0;
  }

  .ws-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #475569;
    flex-shrink: 0;
  }
  .ws-dot.connected { background: #22c55e; }
  .ws-dot.connecting { background: #FFB800; }
  .ws-dot-small {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #475569;
    margin-left: auto;
    flex-shrink: 0;
  }
  .ws-dot-small.connected { background: #22c55e; }
  .ws-dot-small.connecting { background: #FFB800; }

  .channel-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  }

  .ch-item {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 12px 16px;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    color: inherit;
    font-family: inherit;
    font-size: inherit;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    transition: background 0.12s;
    min-height: 60px;
  }

  .ch-item:active {
    background: rgba(0,229,255,0.06);
  }

  .ch-icon {
    font-size: 22px;
    flex-shrink: 0;
    width: 36px;
    text-align: center;
  }

  .ch-info {
    flex: 1;
    min-width: 0;
  }

  .ch-name {
    font-size: 15px;
    font-weight: 600;
    color: #E2E8F0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .ch-preview {
    font-size: 13px;
    color: #64748B;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-top: 2px;
  }

  .ch-role {
    color: #7C3AED;
    font-size: 12px;
  }

  .ch-pulse {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: #34d399;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .ch-pulse-stale {
    color: #475569;
  }

  .pulse-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: #34d399;
    flex-shrink: 0;
    animation: pulseDot 1.5s ease-in-out infinite;
  }

  .pulse-dot-stale {
    background: #475569;
    animation: none;
  }

  @keyframes pulseDot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.7); }
  }

  .empty-tip {
    text-align: center;
    padding: 40px 20px;
    color: #475569;
    font-size: 14px;
  }

  .chat-view {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }

  .chat-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    border-bottom: 1px solid rgba(0,229,255,0.1);
    background: rgba(11,16,30,0.95);
    flex-shrink: 0;
    min-height: 50px;
  }

  .back-btn {
    background: none;
    border: none;
    color: #00E5FF;
    font-size: 20px;
    cursor: pointer;
    padding: 4px 8px;
    min-width: 44px;
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
  }

  .sync-btn {
    background: rgba(0,229,255,0.08);
    border: 1px solid rgba(0,229,255,0.2);
    color: #00E5FF;
    font-size: 16px;
    cursor: pointer;
    padding: 2px 8px;
    min-width: 36px;
    min-height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
  }

  .chat-icon { font-size: 18px; }

  .chat-title {
    flex: 1;
    font-size: 15px;
    font-weight: 600;
    color: #E2E8F0;
  }

  .msg-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    -webkit-overflow-scrolling: touch;
  }

  .empty-chat {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #475569;
    font-size: 13px;
    padding: 40px 20px;
  }

  .bubble-row {
    display: flex;
  }

  .user-row {
    justify-content: flex-end;
  }

  .agent-row {
    justify-content: flex-start;
    gap: 10px;
    align-items: flex-start;
  }

  .bubble {
    max-width: 88%;
    padding: 10px 14px;
    border-radius: 16px;
    font-size: 15px;
    line-height: 1.6;
    word-break: break-word;
  }

  .user-bubble {
    background: linear-gradient(135deg, rgba(0,229,255,0.25), rgba(0,229,255,0.12));
    border: 1px solid rgba(0,229,255,0.3);
    border-radius: 16px 16px 4px 16px;
    color: #E2E8F0;
  }

  .agent-avatar {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
    margin-top: 2px;
  }

  .agent-content {
    flex: 1;
    min-width: 0;
    max-width: 90%;
  }

  .agent-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }

  .agent-name {
    font-size: 13px;
    font-weight: 600;
  }

  .agent-time {
    font-size: 11px;
    color: #64748B;
  }

  .thinking-indicator {
    font-size: 12px;
    color: #64748B;
    font-style: italic;
    margin-bottom: 4px;
  }

  .thinking-block {
    background: rgba(0,0,0,0.3);
    border-radius: 8px;
    border-left: 3px solid rgba(124,58,237,0.5);
    padding: 8px 10px;
    margin-bottom: 8px;
  }

  .thinking-label {
    font-size: 11px;
    color: #7C3AED;
    font-weight: 600;
    margin-bottom: 4px;
  }

  .thinking-text {
    font-size: 12px;
    color: #94A3B8;
    font-style: italic;
    line-height: 1.5;
    max-height: 100px;
    overflow-y: auto;
  }

  .agent-bubble {
    padding: 10px 14px;
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(124,58,237,0.15);
    border-radius: 4px 14px 14px 14px;
    color: #E2E8F0;
    font-size: 15px;
    line-height: 1.7;
    word-break: break-word;
    white-space: pre-wrap;
  }

  .stream-text { white-space: pre-wrap; }

  .cursor {
    animation: blink 0.8s infinite;
    color: #00E5FF;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; } 50% { opacity: 0; }
  }

  .streaming-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #94A3B8;
    padding: 4px 0;
  }

  .dot-pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #7C3AED;
    animation: pulse 1.5s infinite;
    flex-shrink: 0;
  }

  @keyframes pulse {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.2); opacity: 0.6; }
  }

  .new-msg-btn {
    position: sticky;
    bottom: 0;
    margin: 0 14px;
    padding: 10px;
    background: linear-gradient(135deg, rgba(0,229,255,0.2), rgba(0,229,255,0.1));
    border: 1px solid rgba(0,229,255,0.3);
    border-radius: 20px;
    color: #00E5FF;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
    width: calc(100% - 28px);
  }

  .input-area {
    padding: 8px 10px;
    border-top: 1px solid rgba(0,229,255,0.1);
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex-shrink: 0;
    background: rgba(11,16,30,0.95);
  }

  .msg-input {
    width: 100%;
    background: rgba(30,41,59,0.7);
    border: 1px solid rgba(0,229,255,0.2);
    border-radius: 10px;
    padding: 8px 12px;
    color: #F0F9FF;
    font-size: 16px;
    resize: none;
    outline: none;
    line-height: 1.4;
    font-family: inherit;
    min-height: 40px;
    max-height: 100px;
  }

  .msg-input::placeholder { color: #475569; }
  .msg-input:focus { border-color: rgba(0,229,255,0.4); }

  .send-btn {
    width: 100%;
    padding: 10px;
    border-radius: 8px;
    background: linear-gradient(135deg, rgba(0,229,255,0.2), rgba(0,229,255,0.1));
    border: 1px solid rgba(0,229,255,0.3);
    color: #00E5FF;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    min-height: 40px;
    transition: all 0.15s;
  }

  .send-btn.disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
