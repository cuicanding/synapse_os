<script lang="ts">
  import { onMount, onDestroy } from "svelte";

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
  // "list" = 频道/私聊列表，"chat" = 聊天界面
  let view: "list" | "chat" = "list";
  let listTab: "channels" | "dm" = "channels";

  // ─── WS state ────────────────────────────────────────────────────────
  let ws: WebSocket | null = null;
  let wsStatus: "disconnected" | "connecting" | "connected" = "disconnected";
  let channels: Channel[] = [];
  let currentChannelId = "";
  let channelStates: Record<string, ChannelState> = {};
  let joinedChannels: Set<string> = new Set();

  const DEFAULT_STATE: ChannelState = { messages: [], isStreaming: false, unreadCount: 0 };

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
    return channelStates[id] || DEFAULT_STATE;
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

      if (msg.type === "channel_list") {
        channels = msg.channels || [];
        if (channels.length > 0 && !currentChannelId) {
          const first = channels[0].id;
          joinChannel(first);
        }
        return;
      }

      if (msg.type === "channel_joined") {
        currentChannelId = msg.channelId;
        joinedChannels.add(msg.channelId);
        const mapped: Turn[] = (msg.history || []).map((m: any) => ({
          role: m.role,
          type: m.role === "user" ? "user" : "turn",
          content: m.content || "",
          response: m.role === "assistant" ? m.content : "",
          senderId: m.senderId,
          senderName: m.senderName,
          timestamp: m.timestamp,
        }));
        channelStates = {
          ...channelStates,
          [msg.channelId]: { ...(channelStates[msg.channelId] || DEFAULT_STATE), messages: mapped },
        };
        setTimeout(() => scrollToBottom(), 100);
        return;
      }

      if (msg.type === "channel_message") {
        const existing = channelStates[msg.channelId] || DEFAULT_STATE;
        channelStates = {
          ...channelStates,
          [msg.channelId]: {
            ...existing,
            messages: [...existing.messages, {
              role: msg.senderId === "user" ? "user" : "assistant",
              type: msg.senderId === "user" ? "user" : "turn",
              content: msg.content,
              senderId: msg.senderId,
              senderName: msg.senderName,
              timestamp: msg.timestamp,
            }],
            unreadCount: msg.channelId === currentChannelId ? existing.unreadCount : existing.unreadCount + 1,
          },
        };
        if (msg.channelId === currentChannelId) triggerSmartScroll();
        return;
      }

      if (msg.type === "agent_thinking") {
        const tid = msg.channelId || currentChannelId;
        const existing = channelStates[tid] || DEFAULT_STATE;
        const msgs = existing.messages;
        const last = msgs[msgs.length - 1];
        if (!last || last.senderId !== msg.agent || last.type !== "turn" || !last.streaming) {
          channelStates = {
            ...channelStates,
            [tid]: {
              ...existing,
              isStreaming: true,
              messages: [...msgs, {
                role: "assistant", type: "turn", response: "", thinking: "",
                streaming: true, waitingForFirstDelta: true,
                senderId: msg.agent,
                senderName: msg.agentName || AGENT_PROFILES[msg.agent]?.name || msg.agent,
              }],
            },
          };
          if (tid === currentChannelId) triggerSmartScroll();
        }
        return;
      }

      if (msg.type === "session_reset") {
        if (msg.success) {
          channelStates = { ...channelStates, [msg.channelId]: { ...DEFAULT_STATE, messages: [] } };
        }
        return;
      }

      if (["delta", "thinking", "done", "error"].includes(msg.type)) {
        const tid = msg.channelId || currentChannelId;
        const existing = channelStates[tid] || DEFAULT_STATE;
        const msgs = existing.messages;
        const last = msgs[msgs.length - 1];

        if (msg.type === "delta") {
          let newMsgs: Turn[];
          if (!last || last.type !== "turn") {
            newMsgs = [...msgs, { role: "assistant", type: "turn", response: msg.content || "", streaming: true, senderId: msg.agent, senderName: AGENT_PROFILES[msg.agent]?.name || msg.agent }];
          } else {
            newMsgs = msgs.map((m, i) => i === msgs.length - 1 ? { ...m, waitingForFirstDelta: false, response: (m.response || "") + msg.content } : m);
          }
          channelStates = { ...channelStates, [tid]: { ...existing, messages: newMsgs } };
          if (tid === currentChannelId) triggerSmartScroll();
        } else if (msg.type === "thinking") {
          let newMsgs: Turn[];
          if (!last || last.type !== "turn") {
            newMsgs = [...msgs, { role: "assistant", type: "turn", response: "", thinking: msg.content, streaming: true, senderId: msg.agent, senderName: AGENT_PROFILES[msg.agent]?.name || msg.agent }];
          } else {
            newMsgs = msgs.map((m, i) => i === msgs.length - 1 ? { ...m, waitingForFirstDelta: false, thinking: (m.thinking || "") + msg.content } : m);
          }
          channelStates = { ...channelStates, [tid]: { ...existing, messages: newMsgs } };
          if (tid === currentChannelId) triggerSmartScroll();
        } else if (msg.type === "done") {
          const newMsgs = msgs.map((m, i) => i === msgs.length - 1 && m.type === "turn" ? { ...m, streaming: false } : m);
          channelStates = { ...channelStates, [tid]: { ...existing, messages: newMsgs, isStreaming: false } };
          if (tid === currentChannelId) triggerSmartScroll();
        } else if (msg.type === "error") {
          channelStates = {
            ...channelStates,
            [tid]: { ...existing, isStreaming: false, messages: [...msgs, { role: "system", type: "user", content: "❌ " + msg.content }] },
          };
        }
        return;
      }
    };

    ws.onclose = () => { wsStatus = "disconnected"; scheduleReconnect(); };
    ws.onerror = () => { wsStatus = "disconnected"; };
  }

  // ─── Actions ─────────────────────────────────────────────────────────
  function joinChannel(channelId: string) {
    if (channelId === currentChannelId && view === "chat") return;
    currentChannelId = channelId;
    userScrolledAway = false;
    newMsgCount = 0;
    view = "chat";

    if (!joinedChannels.has(channelId)) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "join_channel", channelId }));
      }
    } else {
      channelStates = { ...channelStates, [channelId]: { ...(channelStates[channelId] || DEFAULT_STATE), unreadCount: 0 } };
      setTimeout(scrollToBottom, 100);
    }
  }

  let chatMessage = "";

  function sendMessage() {
    if (!chatMessage.trim() || wsStatus !== "connected" || !currentChannelId) return;
    const msg = chatMessage.trim();
    chatMessage = "";
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "send_message", channelId: currentChannelId, message: msg }));
    }
    const existing = channelStates[currentChannelId] || DEFAULT_STATE;
    channelStates = {
      ...channelStates,
      [currentChannelId]: { ...existing, messages: [...existing.messages, { role: "user", type: "user", content: msg, senderId: "user", senderName: "你" }] },
    };
    if (!userScrolledAway) setTimeout(scrollToBottom, 100);
  }

  function handleInputKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  // ─── Markdown mini renderer ───────────────────────────────────────────
  function parseMarkdown(text: string): string {
    if (!text) return "";
    return text
      .replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre style="background:rgba(0,0,0,0.4);padding:8px;border-radius:6px;overflow-x:auto;margin:6px 0;font-size:12px;"><code>$2</code></pre>')
      .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#fff;">$1</strong>')
      .replace(/`(.+?)`/g, '<code style="background:rgba(0,0,0,0.3);padding:1px 4px;border-radius:3px;font-size:12px;">$1</code>')
      .replace(/^### (.+)$/gm, '<div style="font-size:14px;font-weight:700;color:#fff;margin:10px 0 4px;">$1</div>')
      .replace(/^## (.+)$/gm, '<div style="font-size:15px;font-weight:700;color:#fff;margin:12px 0 6px;">$1</div>')
      .replace(/^# (.+)$/gm, '<div style="font-size:16px;font-weight:700;color:#fff;margin:14px 0 6px;">$1</div>')
      .replace(/^- (.+)$/gm, '<div style="padding-left:10px;margin:2px 0;">• $1</div>')
      .replace(/\n/g, "<br/>");
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
    const msgs = getState(channelId).messages;
    if (!msgs.length) return "暂无消息";
    const last = msgs[msgs.length - 1];
    const text = last.content || last.response || "";
    return text.slice(0, 30) + (text.length > 30 ? "…" : "");
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────
  onMount(() => {
    connectWs();
    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      // 不关闭 WS，保持后台接收
    };
  });
  onDestroy(() => {
    if (reconnectTimer) clearTimeout(reconnectTimer);
  });
</script>

<div class="wb-root">
  {#if view === "list"}
    <!-- ─── 频道列表视图 ─────────────────────────── -->
    <div class="list-view">
      <!-- 子 Tab -->
      <div class="sub-tabs">
        <button class="sub-tab {listTab === 'channels' ? 'active' : ''}" on:click={() => { listTab = 'channels'; }}>
          频道
        </button>
        <button class="sub-tab {listTab === 'dm' ? 'active' : ''}" on:click={() => { listTab = 'dm'; }}>
          私聊
        </button>
      </div>

      <!-- WS 状态 -->
      <div class="ws-bar">
        <span class="ws-dot {wsStatus}"></span>
        <span class="ws-text">{wsStatus === 'connected' ? '已连接' : wsStatus === 'connecting' ? '连接中...' : '未连接'}</span>
      </div>

      <div class="channel-list">
        {#if listTab === 'channels'}
          {#each domainChannels as ch}
            {@const state = getState(ch.id)}
            <button class="ch-item {currentChannelId === ch.id ? 'selected' : ''}" on:click={() => joinChannel(ch.id)}>
              <span class="ch-icon">{ch.icon}</span>
              <div class="ch-info">
                <div class="ch-name">{ch.name}</div>
                <div class="ch-preview">{lastMessage(ch.id)}</div>
              </div>
              {#if state.unreadCount > 0}
                <span class="unread-badge">{state.unreadCount > 99 ? '99+' : state.unreadCount}</span>
              {/if}
            </button>
          {/each}
          {#if domainChannels.length === 0}
            <div class="empty-tip">加载中...</div>
          {/if}
        {:else}
          <!-- 私聊列表 -->
          {#each Object.entries(AGENT_PROFILES) as [agentId, profile]}
            {@const dmId = `dm-${agentId}`}
            {@const state = getState(dmId)}
            <button class="ch-item {currentChannelId === dmId ? 'selected' : ''}" on:click={() => joinChannel(dmId)}>
              <span class="ch-icon">{profile.emoji}</span>
              <div class="ch-info">
                <div class="ch-name">{profile.name}</div>
                <div class="ch-preview ch-role">{profile.role}</div>
              </div>
              {#if state.unreadCount > 0}
                <span class="unread-badge">{state.unreadCount > 99 ? '99+' : state.unreadCount}</span>
              {/if}
            </button>
          {/each}
        {/if}
      </div>
    </div>

  {:else}
    <!-- ─── 聊天视图 ─────────────────────────────── -->
    {@const state = getState(currentChannelId)}
    <div class="chat-view">
      <!-- 聊天顶栏 -->
      <div class="chat-header">
        <button class="back-btn" on:click={() => { view = 'list'; }}>←</button>
        <span class="chat-icon">{getChannelIcon(currentChannelId)}</span>
        <span class="chat-title">{getChannelLabel(currentChannelId)}</span>
        <span class="ws-dot-small {wsStatus}"></span>
      </div>

      <!-- 消息列表 -->
      <div
        class="msg-list"
        bind:this={chatScrollEl}
        on:scroll={handleScroll}
      >
        {#if state.messages.length === 0}
          <div class="empty-chat">
            <div style="font-size:28px;margin-bottom:8px;">💬</div>
            <div>发送消息开始对话</div>
          </div>
        {/if}

        {#each state.messages as item}
          {#if item.type === "user"}
            <!-- 用户气泡（靠右蓝色） -->
            <div class="bubble-row user-row">
              <div class="bubble user-bubble">
                {item.content || ""}
              </div>
            </div>
          {:else if item.type === "turn"}
            <!-- Agent 消息（靠左深色卡片） -->
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

        {#if state.isStreaming}
          <div class="streaming-indicator">
            <span class="dot-pulse"></span>AI 正在回复中...
          </div>
        {/if}
      </div>

      <!-- 新消息提示 -->
      {#if userScrolledAway && newMsgCount > 0}
        <button class="new-msg-btn" on:click={() => { userScrolledAway = false; newMsgCount = 0; scrollToBottom(); }}>
          ⬇ {newMsgCount} 条新消息
        </button>
      {/if}

      <!-- 输入区 -->
      <div class="input-area">
        <textarea
          bind:value={chatMessage}
          on:keydown={handleInputKeydown}
          placeholder="发送消息... (Enter 发送)"
          rows={3}
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

  /* ─── List View ──────────────────────────── */
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

  .ch-item:active, .ch-item.selected {
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

  .unread-badge {
    background: #ef4444;
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    border-radius: 10px;
    padding: 2px 7px;
    flex-shrink: 0;
  }

  .empty-tip {
    text-align: center;
    padding: 40px 20px;
    color: #475569;
    font-size: 14px;
  }

  /* ─── Chat View ──────────────────────────── */
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
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 14px;
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

  /* ─── Bubbles ────────────────────────────── */
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
    max-width: 78%;
    padding: 10px 14px;
    border-radius: 16px;
    font-size: 14px;
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
    font-size: 14px;
    line-height: 1.7;
    word-break: break-word;
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

  /* ─── Input Area ─────────────────────────── */
  .input-area {
    padding: 10px 14px;
    border-top: 1px solid rgba(0,229,255,0.1);
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex-shrink: 0;
  }

  .msg-input {
    width: 100%;
    background: rgba(30,41,59,0.7);
    border: 1px solid rgba(0,229,255,0.2);
    border-radius: 10px;
    padding: 10px 12px;
    color: #F0F9FF;
    font-size: 16px; /* iOS 防缩放 */
    resize: none;
    outline: none;
    line-height: 1.5;
    font-family: inherit;
    min-height: 80px;
  }

  .msg-input::placeholder { color: #475569; }
  .msg-input:focus { border-color: rgba(0,229,255,0.4); }

  .send-btn {
    width: 100%;
    padding: 12px;
    border-radius: 8px;
    background: linear-gradient(135deg, rgba(0,229,255,0.2), rgba(0,229,255,0.1));
    border: 1px solid rgba(0,229,255,0.3);
    color: #00E5FF;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    min-height: 44px;
    transition: all 0.15s;
  }

  .send-btn.disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
