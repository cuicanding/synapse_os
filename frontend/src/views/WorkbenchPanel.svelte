<script lang="ts">
  import { onMount, onDestroy } from "svelte";

  // ========== 类型定义 ==========
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

  interface AgentState {
    turns: Turn[];
    queue: string[];
    isStreaming: boolean;
  }

  interface Channel {
    id: string;
    name: string;
    icon: string;
    type: "domain" | "dm";
    members: ChannelMember[];
  }

  interface ChannelMember {
    id: string;
    name: string;
    status: "online" | "offline";
    role: string;
    emoji: string;
    color: string;
  }

  interface ChannelState {
    messages: Turn[];
    members: ChannelMember[];
    isStreaming: boolean;
    unreadCount: number;
  }

  // ========== 状态变量 ==========
  let ws: WebSocket | null = null;
  let wsStatus: "disconnected" | "connecting" | "connected" = "disconnected";
  let chatMessage = "";
  let currentChannelId = "";

  // Reactive: keep currentChannelState in sync
  let currentChannelState: ChannelState = { messages: [], members: [], isStreaming: false, unreadCount: 0 };
  $: {
    const s = channelStates[currentChannelId] || DEFAULT_CHANNEL_STATE;
    currentChannelState = { ...s };
  }
  let userScrolledAway = false;
  let newMsgCount = 0;
  let chatScrollEl: HTMLDivElement;

  // 频道相关状态
  let channels: Channel[] = [];
  let expandedChannel: string = "__ALL__";  // 默认展开所有频道
  let channelStates: Record<string, ChannelState> = {};
  let joinedChannels: Set<string> = new Set();

  // 旧的 Agent 状态（用于兼容）
  let agentStates: Record<string, AgentState> = {
    main: { turns: [], queue: [], isStreaming: false },
    susan: { turns: [], queue: [], isStreaming: false },
    reed: { turns: [], queue: [], isStreaming: false },
  };

  // Agent 配置
  const AGENT_PROFILES = {
    main: { name: '果爸', emoji: '🎯', color: '#FFB800', role: '董事长' },
    susan: { name: '苏珊', emoji: '🎨', color: '#7C3AED', role: '主设计师' },
    reed: { name: '里德', emoji: '🔧', color: '#00E5FF', role: '架构师' },
  };

  const agents = [
    { id: "main", name: "果爸", emoji: "👑", desc: "总经理", color: "#f59e0b" },
    { id: "susan", name: "苏珊", emoji: "🎯", desc: "产品设计师", color: "#06b6d4" },
    { id: "reed", name: "里德", emoji: "🔧", desc: "架构师/开发", color: "#8b5cf6" },
  ];

  // ========== 辅助函数 ==========
  function getState(agentId: string): AgentState {
    if (!agentStates[agentId]) {
      agentStates[agentId] = { turns: [], queue: [], isStreaming: false };
    }
    return agentStates[agentId];
  }

  // 默认频道状态
  const DEFAULT_CHANNEL_STATE: ChannelState = { messages: [], members: [], isStreaming: false, unreadCount: 0 };

  // 获取频道状态（仅用于读取，不用于修改）
  function getChannelState(channelId: string): ChannelState {
    return channelStates[channelId] || DEFAULT_CHANNEL_STATE;
  }

  function getCurrentChannel(): Channel | undefined {
    return channels.find(c => c.id === currentChannelId);
  }

  function getCurrentChannelState(): ChannelState {
    return getChannelState(currentChannelId);
  }

  function parseMarkdown(text: string): string {
    if (!text) return "";
    return text
      .replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre style="background:rgba(0,0,0,0.4);padding:10px;border-radius:6px;overflow-x:auto;margin:8px 0;font-size:12px;"><code>$2</code></pre>')
      .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#fff;">$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code style="background:rgba(0,0,0,0.3);padding:1px 5px;border-radius:3px;font-family:monospace;font-size:12px;">$1</code>')
      .replace(/^### (.+)$/gm, '<div style="font-size:15px;font-weight:700;color:#fff;margin:12px 0 6px;">$1</div>')
      .replace(/^## (.+)$/gm, '<div style="font-size:16px;font-weight:700;color:#fff;margin:14px 0 8px;">$1</div>')
      .replace(/^# (.+)$/gm, '<div style="font-size:17px;font-weight:700;color:#fff;margin:16px 0 8px;">$1</div>')
      .replace(/^- (.+)$/gm, '<div style="padding-left:12px;margin:2px 0;">• $1</div>')
      .replace(/^\d+\. (.+)$/gm, '<div style="padding-left:12px;margin:2px 0;">$1</div>')
      .replace(/\n/g, '<br/>');
  }

  function isAtBottom(): boolean {
    if (!chatScrollEl) return true;
    return chatScrollEl.scrollHeight - chatScrollEl.scrollTop - chatScrollEl.clientHeight < 80;
  }
  function scrollToBottom() {
    if (!chatScrollEl) return;
    chatScrollEl.scrollTo({ top: chatScrollEl.scrollHeight, behavior: 'smooth' });
  }
  function handleScroll() {
    if (!chatScrollEl) return;
    if (isAtBottom()) { userScrolledAway = false; newMsgCount = 0; }
    else { userScrolledAway = true; }
  }
  function triggerSmartScroll() {
    if (!userScrolledAway) { setTimeout(() => scrollToBottom(), 30); }
    else { newMsgCount++; }
  }

  // ==================== WebSocket ====================
  function connectChatWs() {
    if (ws && ws.readyState === WebSocket.OPEN) return;
    wsStatus = "connecting";
    var wsHost = window.location.hostname;
    var wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(wsProtocol + "//" + wsHost + ":" + window.location.port + "/ws/chat");

    ws.onopen = function() { wsStatus = "connected"; };

    ws.onmessage = function(event) {
      var msg = JSON.parse(event.data);

      // 新的频道消息协议
      if (msg.type === "channel_list") {
        channels = msg.channels || [];
        // 默认加入第一个频道
        if (channels.length > 0 && !currentChannelId) {
          currentChannelId = channels[0].id;
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "join_channel", channelId: currentChannelId }));
          }
        }
        return;
      }

      if (msg.type === "channel_joined") {
        console.log('[chat] channel_joined:', msg.channelId, 'members:', (msg.members || []).length);
        currentChannelId = msg.channelId;
        joinedChannels.add(msg.channelId);
        
        // 使用深拷贝创建新对象，确保 Svelte 能检测到变更
        channelStates = {
          ...channelStates,
          [msg.channelId]: {
            ...(channelStates[msg.channelId] || DEFAULT_CHANNEL_STATE),
            members: msg.members || [],
            messages: (msg.history || []).map(function(m) {
              return {
                role: m.role,
                type: m.role === "user" ? "user" : "turn",
                content: m.content || "",
                response: m.role === "assistant" ? m.content : "",
                senderId: m.senderId,
                senderName: m.senderName,
                timestamp: m.timestamp
              };
            })
          }
        };
        setTimeout(function() { scrollToBottom(); }, 100);
        return;
      }

      if (msg.type === "channel_message") {
        var existingState = channelStates[msg.channelId] || DEFAULT_CHANNEL_STATE;
        var newMessages = [...existingState.messages, {
          role: msg.senderId === "user" ? "user" : "assistant",
          type: msg.senderId === "user" ? "user" : "turn",
          content: msg.content,
          senderId: msg.senderId,
          senderName: msg.senderName,
          timestamp: msg.timestamp
        }];
        
        channelStates = {
          ...channelStates,
          [msg.channelId]: {
            ...existingState,
            messages: newMessages,
            unreadCount: msg.channelId === currentChannelId ? existingState.unreadCount : existingState.unreadCount + 1
          }
        };
        
        if (msg.channelId === currentChannelId) {
          triggerSmartScroll();
        }
        return;
      }

      // Agent 开始思考通知（在 chat.send 成功后立即发送）
      if (msg.type === "agent_thinking") {
        var targetChannelId = msg.channelId || currentChannelId;
        var existingState = channelStates[targetChannelId] || DEFAULT_CHANNEL_STATE;
        var messages = existingState.messages;
        var last = messages[messages.length - 1];

        // 如果最后一条消息不是该 agent 的 streaming turn，则创建一个新的占位 turn
        if (!last || last.senderId !== msg.agent || last.type !== "turn" || !last.streaming) {
          var newMessages = [...messages, {
            role: "assistant",
            type: "turn",
            response: "",
            thinking: "",
            streaming: true,
            waitingForFirstDelta: true,
            senderId: msg.agent,
            senderName: msg.agentName || AGENT_PROFILES[msg.agent]?.name || msg.agent
          }];
          channelStates = {
            ...channelStates,
            [targetChannelId]: {
              ...existingState,
              messages: newMessages,
              isStreaming: true
            }
          };
          if (targetChannelId === currentChannelId) {
            triggerSmartScroll();
          }
        }
        return;
      }

      // Session 重置响应
      if (msg.type === "session_reset") {
        if (msg.success) {
          // 清空对应频道的消息
          channelStates = {
            ...channelStates,
            [msg.channelId]: { ...DEFAULT_CHANNEL_STATE, messages: [] }
          };
        }
        return;
      }

      // 流式消息处理（绑定到频道）
      if (msg.type === "delta" || msg.type === "thinking" || msg.type === "done" || msg.type === "error") {
        var targetChannelId = msg.channelId || currentChannelId;
        var existingState = channelStates[targetChannelId] || DEFAULT_CHANNEL_STATE;
        var messages = existingState.messages;
        var last = messages[messages.length - 1];
        
        if (msg.type === "delta") {
          var newMessages;
          if (!last || last.type !== "turn") {
            newMessages = [...messages, { 
              role: "assistant", 
              type: "turn", 
              response: msg.content || "", 
              streaming: true,
              senderId: msg.agent,
              senderName: AGENT_PROFILES[msg.agent]?.name || msg.agent
            }];
          } else {
            newMessages = messages.map((m, i) => 
              i === messages.length - 1 
                ? { ...m, waitingForFirstDelta: false, response: (m.response || "") + msg.content }
                : m
            );
          }
          channelStates = {
            ...channelStates,
            [targetChannelId]: { ...existingState, messages: newMessages }
          };
          if (targetChannelId === currentChannelId) {
            triggerSmartScroll();
          }
        } else if (msg.type === "thinking") {
          var newMessages;
          if (!last || last.type !== "turn") {
            newMessages = [...messages, { 
              role: "assistant", 
              type: "turn", 
              response: "", 
              thinking: msg.content,
              streaming: true,
              senderId: msg.agent,
              senderName: AGENT_PROFILES[msg.agent]?.name || msg.agent
            }];
          } else {
            newMessages = messages.map((m, i) => 
              i === messages.length - 1 
                ? { ...m, waitingForFirstDelta: false, thinking: (m.thinking || "") + msg.content }
                : m
            );
          }
          channelStates = {
            ...channelStates,
            [targetChannelId]: { ...existingState, messages: newMessages }
          };
          if (targetChannelId === currentChannelId) {
            triggerSmartScroll();
          }
        } else if (msg.type === "done") {
          var newMessages = messages.map((m, i) => 
            i === messages.length - 1 && m.type === "turn"
              ? { ...m, streaming: false }
              : m
          );
          channelStates = {
            ...channelStates,
            [targetChannelId]: { ...existingState, messages: newMessages, isStreaming: false }
          };
          if (targetChannelId === currentChannelId) {
            triggerSmartScroll();
          }
        } else if (msg.type === "error") {
          var newMessages = [...messages, { 
            role: "system", 
            type: "user", 
            content: "❌ " + msg.content,
            senderId: msg.agent,
            senderName: AGENT_PROFILES[msg.agent]?.name || msg.agent
          }];
          channelStates = {
            ...channelStates,
            [targetChannelId]: { ...existingState, messages: newMessages, isStreaming: false }
          };
        }
        return;
      }
    };

    ws.onclose = function() { wsStatus = "disconnected"; };
    ws.onerror = function() { wsStatus = "disconnected"; };
  }

  // ==================== Actions ====================

  function resetSession() {
    if (!currentChannelId || !currentChannelId.startsWith('dm-') || wsStatus !== 'connected') return;
    if (!confirm('重置后当前对话历史将清空，agent 将重新加载身份配置，确定吗？')) return;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "reset_session", channelId: currentChannelId }));
    }
  }

  function sendMessage() {
    if (!chatMessage.trim() || wsStatus !== "connected" || !currentChannelId) return;
    var msg = chatMessage.trim();
    chatMessage = "";

    // 发送到当前频道
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ 
        type: "send_message", 
        channelId: currentChannelId, 
        message: msg 
      }));
    }

    // 添加到本地消息列表（使用深拷贝确保响应式）
    var existingState = channelStates[currentChannelId] || DEFAULT_CHANNEL_STATE;
    channelStates = {
      ...channelStates,
      [currentChannelId]: {
        ...existingState,
        messages: [...existingState.messages, { 
          role: "user", 
          type: "user", 
          content: msg,
          senderId: "user",
          senderName: "你"
        }]
      }
    };
    
    if (!userScrolledAway) { 
      setTimeout(() => scrollToBottom(), 100);
    }
  }

  function joinChannel(channelId: string) {
    if (channelId === currentChannelId) return;
    
    currentChannelId = channelId;
    userScrolledAway = false;
    newMsgCount = 0;
    
    // 如果还没加入过这个频道，则发送加入请求
    if (!joinedChannels.has(channelId)) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "join_channel", channelId: channelId }));
      }
    } else {
      // 已经加入过，直接切换并清零未读计数（使用深拷贝确保响应式）
      var existingState = channelStates[channelId] || DEFAULT_CHANNEL_STATE;
      channelStates = {
        ...channelStates,
        [channelId]: {
          ...existingState,
          unreadCount: 0
        }
      };
      setTimeout(scrollToBottom, 100);
    }
  }


  // ==================== Lifecycle ====================
  onMount(function() {
    connectChatWs();
    if (chatScrollEl) { chatScrollEl.addEventListener('scroll', handleScroll); }
    return () => {
      if (ws) { ws.close(); ws = null; }
      if (chatScrollEl) { chatScrollEl.removeEventListener('scroll', handleScroll); }
    };
  });

  onDestroy(function() {});
</script>

<!-- 三栏布局容器 -->
<div style="height:100%;min-height:0;display:flex;background:rgba(11,16,30,0.98);">
  
  <!-- 频道侧栏 (200px) -->
  <div style="width:200px;background:rgba(11,16,30,0.98);border-right:1px solid rgba(0,229,255,0.1);display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto;">
    <!-- 频道列表标题 -->
    <div style="padding:16px 12px 8px;display:flex;align-items:center;justify-content:space-between;">
      <span style="font-size:12px;font-weight:600;color:#00e5ff;text-transform:uppercase;letter-spacing:1px;">💬 频道</span>
      <button
        type="button"
        on:click|stopPropagation={() => {
          if (currentChannelId && ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'join_channel', channelId: currentChannelId }));
          }
        }}
        style="padding:2px 8px;font-size:11px;color:#64748b;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:4px;cursor:pointer;"
        title="同步当前频道"
      >
        ⟳ 同步
      </button>
    </div>

    <!-- 频道列表 -->
    <div style="padding:0 8px;">
      <!-- 果爸单独入口 -->
      {#each [{ id: 'dm-main', name: '果爸', icon: '👑' }] as mainItem}
        {@const mainDmId = mainItem.id}
        {@const isMainSelected = currentChannelId === mainDmId}
        {@const mainChannelState = getChannelState(mainDmId)}
        <button
          type="button"
          on:click|stopPropagation={() => joinChannel(mainDmId)}
          style="display:flex;align-items:center;gap:6px;width:100%;padding:8px 10px;margin-bottom:2px;border-radius:6px;border-left:{isMainSelected ? '3px solid #FFB800' : '3px solid transparent'};border:none;cursor:pointer;text-align:left;color:inherit;font-family:inherit;font-size:inherit;background:{isMainSelected ? 'rgba(255,184,0,0.1)' : 'transparent'};transition:background 0.15s;"
        >
          <span style="font-size:15px;">{mainItem.icon}</span>
          <span style="flex:1;font-size:13px;font-weight:600;color:{isMainSelected ? '#FFB800' : '#e2e8f0'};">
            {mainItem.name}
          </span>
          {#if mainChannelState.unreadCount > 0}
            <span style="background:#ef4444;color:#fff;font-size:10px;font-weight:700;border-radius:8px;padding:1px 6px;min-width:16px;height:16px;display:flex;align-items:center;justify-content:center;">
              {mainChannelState.unreadCount > 99 ? '99+' : mainChannelState.unreadCount}
            </span>
          {/if}
        </button>
      {/each}

      <!-- 分隔线 -->
      <div style="margin:4px 8px 6px;border-top:1px solid rgba(0,229,255,0.08);"></div>

      {#each channels.filter(c => c.type === 'domain') as channel}
        {@const isSelected = currentChannelId === channel.id}
        {@const channelState = getChannelState(channel.id)}
        {@const isExpanded = expandedChannel === "__ALL__" || expandedChannel === channel.id}
        {@const allMembers = channel.members || channelState.members || []}
        {@const onlineCount = allMembers.filter(m => m.status === 'online').length}

        <!-- 频道行：点击频道名进入群聊 -->
        <div style="margin-bottom:1px;">
          <div style="display:flex;align-items:center;border-radius:6px;overflow:hidden;{isSelected && !isExpanded ? 'background:rgba(0,229,255,0.1);' : ''}">
            <!-- 展开箭头 -->
            <button
              type="button"
              on:click|stopPropagation={() => { expandedChannel = isExpanded ? '' : channel.id; }}
              style="width:24px;height:36px;display:flex;align-items:center;justify-content:center;background:none;border:none;cursor:pointer;color:#475569;font-size:10px;transition:transform 0.2s;{isExpanded ? 'transform:rotate(90deg);' : ''}"
            >▶</button>
            <!-- 频道名 -->
            <button
              type="button"
              on:click|stopPropagation={() => joinChannel(channel.id)}
              style="flex:1;display:flex;align-items:center;gap:6px;padding:0 6px;height:36px;background:none;border:none;border-left:{isSelected ? '3px solid #00e5ff' : '3px solid transparent'};cursor:pointer;text-align:left;color:inherit;font-family:inherit;font-size:inherit;"
            >
              <span style="font-size:15px;">{channel.icon}</span>
              <span style="flex:1;font-size:13px;font-weight:500;color:{isSelected ? '#e2e8f0' : '#94a3b8'};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                {channel.name}
              </span>
              <!-- 在线人数 -->
              <span style="font-size:10px;color:{onlineCount > 0 ? '#22c55e' : '#475569'};background:{onlineCount > 0 ? 'rgba(34,197,94,0.1)' : 'rgba(100,116,139,0.1)'};padding:1px 6px;border-radius:8px;">
                {onlineCount}
              </span>
              <!-- 未读数 -->
              {#if channelState.unreadCount > 0}
                <span style="background:#ef4444;color:#fff;font-size:10px;font-weight:700;border-radius:8px;padding:1px 6px;min-width:16px;height:16px;display:flex;align-items:center;justify-content:center;">
                  {channelState.unreadCount > 99 ? '99+' : channelState.unreadCount}
                </span>
              {/if}
            </button>
          </div>

          <!-- 展开的成员列表 -->
          {#if isExpanded}
            {@const onlineMembers = allMembers.filter(m => m.status === 'online')}
            {@const offlineMembers = allMembers.filter(m => m.status === 'offline')}

            <div style="padding:2px 0 4px 24px;">
              <!-- 在线成员 -->
              {#each onlineMembers as member}
                {@const dmId = 'dm-' + (member.id || '')}
                {@const isDmSelected = currentChannelId === dmId}
                <button
                  type="button"
                  on:click|stopPropagation={() => joinChannel(dmId)}
                  class="dm-member-btn"
                  style="display:flex;align-items:center;gap:6px;width:100%;padding:5px 8px;margin-bottom:1px;border-radius:5px;border:none;cursor:pointer;text-align:left;color:inherit;font-family:inherit;font-size:inherit;{isDmSelected ? 'background:rgba(0,229,255,0.15);' : ''}"
                >
                  <div style="width:7px;height:7px;border-radius:50%;background:#22c55e;flex-shrink:0;"></div>
                  <span style="font-size:12px;color:{isDmSelected ? '#e2e8f0' : '#94a3b8'};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                    {member.name}
                  </span>
                  {#if isDmSelected}
                    <button
                      type="button"
                      on:click|stopPropagation={() => resetSession()}
                      title="重置对话"
                      style="width:18px;height:18px;display:flex;align-items:center;justify-content:center;background:none;border:none;cursor:pointer;color:#64748b;font-size:11px;padding:0;flex-shrink:0;border-radius:3px;transition:color 0.15s;"
                      on:mouseenter={(e) => e.currentTarget.style.color = '#00e5ff'}
                      on:mouseleave={(e) => e.currentTarget.style.color = '#64748b'}
                    >🔄</button>
                  {/if}
                </button>
              {/each}

              <!-- 离线成员 -->
              {#if offlineMembers.length > 0}
                <div style="margin:6px 0 4px;padding-top:4px;border-top:1px solid rgba(100,116,139,0.15);font-size:10px;color:#475569;padding-left:4px;">
                  离线
                </div>
                {#each offlineMembers as member}
                  <div style="display:flex;align-items:center;gap:6px;padding:4px 8px;opacity:0.5;">
                    <div style="width:7px;height:7px;border-radius:50%;background:#475569;flex-shrink:0;"></div>
                    <span style="font-size:12px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                      {member.name}
                    </span>
                  </div>
                {/each}
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  </div>

  <!-- 主内容区域 (flex-1) -->
  <div style="flex:1;min-width:0;display:flex;flex-direction:column;">
    <!-- 消息区域 -->
    <div bind:this={chatScrollEl} style="flex:1;min-width:0;overflow-y:auto;display:flex;flex-direction:column;gap:16px;padding:16px 20px;">
      {#if currentChannelId}
        
        {#if currentChannelState.messages.length === 0}
          <div style="text-align:center;padding:60px 20px;color:#475569;">
            <div style="font-size:28px;margin-bottom:8px;">💬</div>
            <div style="font-size:13px;">发送消息开始对话</div>
          </div>
        {/if}

        {#each currentChannelState.messages as item, i}
          {#if item.type === "user"}
            <!-- 用户消息 (靠右) -->
            <div style="display:flex;justify-content:flex-end;">
              <div style="max-width:75%;background:linear-gradient(135deg,rgba(0,229,255,0.2),rgba(0,229,255,0.1));border:1px solid rgba(0,229,255,0.3);border-radius:16px 16px 4px 16px;padding:12px 16px;color:#e2e8f0;font-size:14px;line-height:1.6;box-shadow:0 4px 12px rgba(0,229,255,0.1);">
                {item.content}
              </div>
            </div>

          {:else if item.type === "turn"}
            <!-- AI Agent 消息 (靠左) -->
            <div style="display:flex;gap:12px;align-items:flex-start;">
              <!-- Agent 头像 -->
              <div style="width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,{AGENT_PROFILES[item.senderId]?.color || '#7c3aed'},{AGENT_PROFILES[item.senderId]?.color || '#7c3aed'}88);display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0;box-shadow:0 2px 8px rgba(0,0,0,0.3);">
                {AGENT_PROFILES[item.senderId]?.emoji || '🤖'}
              </div>
              
              <div style="flex:1;min-width:0;">
                <!-- 发送者信息 -->
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                  <span style="font-size:13px;font-weight:600;color:{AGENT_PROFILES[item.senderId]?.color || '#7c3aed'};">
                    {item.senderName || AGENT_PROFILES[item.senderId]?.name || item.senderId}
                  </span>
                  <span style="font-size:11px;color:#64748b;">
                    {item.timestamp ? new Date(item.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''}
                  </span>
                </div>

                <!-- 思考状态 -->
                {#if item.waitingForFirstDelta}
                  <div style="margin-bottom:8px;display:flex;align-items:center;gap:6px;">
                    <span style="font-size:12px;color:#64748b;font-style:italic;">
                      💭 正在思考<span class="dots">...</span>
                    </span>
                  </div>
                {/if}

                <!-- 思考过程 -->
                {#if item.thinking}
                  {#if item.streaming && !item.response}
                    <!-- 实时显示思考过程 -->
                    <div style="margin-bottom:12px;padding:10px 12px;background:rgba(0,0,0,0.3);border-radius:8px;border-left:3px solid rgba(124,58,237,0.5);">
                      <div style="font-size:11px;color:#7c3aed;margin-bottom:6px;font-weight:600;">💭 思考中...</div>
                      <div style="font-size:13px;color:#94a3b8;line-height:1.6;white-space:pre-wrap;word-break:break-word;font-style:italic;max-height:140px;overflow-y:auto;">
                        {item.thinking}
                      </div>
                    </div>
                  {:else}
                    <!-- 折叠显示思考过程 -->
                    <details style="margin-bottom:12px;">
                      <summary style="font-size:12px;color:#64748b;cursor:pointer;user-select:none;padding:6px 0;">💭 查看思考过程</summary>
                      <div style="margin-top:8px;padding:10px 12px;background:rgba(0,0,0,0.3);border-radius:8px;font-size:13px;color:#94a3b8;line-height:1.6;white-space:pre-wrap;word-break:break-word;font-style:italic;max-height:200px;overflow-y:auto;">
                        {item.thinking}
                      </div>
                    </details>
                  {/if}
                {/if}

                <!-- 回复内容 -->
                {#if item.response || item.streaming}
                  <div style="padding:12px 16px;background:rgba(45,45,65,0.7);border:1px solid rgba(124,58,237,0.15);border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.2);">
                    <div style="color:#e2e8f0;font-size:14px;line-height:1.7;" class="md-body">
                      {#if item.streaming}
                        <span style="white-space:pre-wrap;word-break:break-word;">{item.response || ''}<span class="cursor-blink">▋</span></span>
                      {:else}
                        {@html parseMarkdown(item.response || '')}
                      {/if}
                    </div>
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        {/each}

        <!-- 流式状态指示器 -->
        {#if currentChannelState.isStreaming}
          <div style="display:flex;align-items:center;gap:8px;padding:8px 16px;background:rgba(124,58,237,0.1);border-radius:20px;border:1px solid rgba(124,58,237,0.2);align-self:flex-start;">
            <div style="width:8px;height:8px;border-radius:50%;background:#7c3aed;animation:pulse 1.5s infinite;"></div>
            <span style="font-size:12px;color:#c4b5fd;">AI 正在回复中...</span>
          </div>
        {/if}

      {:else}
        <!-- 无频道选择时的占位符 -->
        <div style="text-align:center;padding:60px 20px;color:#475569;">
          <div style="font-size:28px;margin-bottom:8px;">💬</div>
          <div style="font-size:13px;">请选择一个频道开始对话</div>
        </div>
      {/if}
    </div>

    <!-- 智能滚动提示 -->
    {#if userScrolledAway && newMsgCount > 0}
      <div style="position:sticky;bottom:0;left:0;right:0;margin:0 20px -8px;z-index:10;">
        <button
          on:click={function() { userScrolledAway = false; newMsgCount = 0; scrollToBottom(); }}
          style="width:100%;padding:10px 16px;background:linear-gradient(135deg,rgba(0,229,255,0.2),rgba(0,229,255,0.1));border:1px solid rgba(0,229,255,0.3);border-radius:20px;color:#00e5ff;font-size:13px;font-weight:600;cursor:pointer;text-align:center;backdrop-filter:blur(10px);box-shadow:0 4px 12px rgba(0,229,255,0.15);"
        >
          ⬇ {newMsgCount} 条新消息
        </button>
      </div>
    {/if}

    <!-- 输入区域 -->
    <div style="padding:16px 20px;border-top:1px solid rgba(0,229,255,0.1);flex-shrink:0;">
      <textarea
        bind:value={chatMessage}
        placeholder={currentChannelId ? "输入消息... (Enter 发送, Shift+Enter 换行)" : "请先选择一个频道"}
        on:keydown={function(e) { 
          if (e.key === 'Enter' && !e.shiftKey && currentChannelId) { 
            e.preventDefault(); 
            sendMessage(); 
          }
        }}
        disabled={!currentChannelId}
        style="width:100%;min-height:120px;max-height:300px;background:rgba(30,41,59,0.6);border:1px solid rgba(0,229,255,0.2);border-radius:12px;padding:12px 14px;color:#e2e8f0;font-size:14px;resize:vertical;outline:none;line-height:1.6;font-family:inherit;transition:all 0.2s;{!currentChannelId ? 'opacity:0.5;' : ''}"
      ></textarea>
      <button
        on:click={sendMessage}
        disabled={wsStatus !== 'connected' || !chatMessage.trim() || !currentChannelId}
        style="width:100%;margin-top:10px;padding:12px;border-radius:8px;background:{wsStatus !== 'connected' || !currentChannelId ? 'rgba(100,116,139,0.1)' : 'linear-gradient(135deg,rgba(0,229,255,0.2),rgba(0,229,255,0.1))'};border:1px solid rgba(0,229,255,0.3);color:{wsStatus !== 'connected' || !currentChannelId ? '#475569' : '#00e5ff'};font-weight:600;font-size:14px;cursor:{wsStatus !== 'connected' || !currentChannelId ? 'not-allowed' : 'pointer'};transition:all 0.2s;"
      >
        {currentChannelId ? '发送消息' : '请选择频道'}
      </button>
    </div>
  </div>
</div>

<style>
  .dots { animation: blink 1.2s infinite; }
  @keyframes blink {
    0%, 20% { opacity: 0.2; }
    50% { opacity: 1; }
    80%, 100% { opacity: 0.2; }
  }
  .cursor-blink { animation: cursorblink 0.8s infinite; color: #00e5ff; }
  @keyframes cursorblink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }
  .md-body :global(strong) { color: #fff; }
  
  /* 新增动画 */
  @keyframes pulse {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.1); opacity: 0.7; }
  }
  
  /* 滚动条样式 */
  div::-webkit-scrollbar {
    width: 6px;
  }
  div::-webkit-scrollbar-track {
    background: rgba(30,41,59,0.3);
    border-radius: 3px;
  }
  div::-webkit-scrollbar-thumb {
    background: rgba(0,229,255,0.3);
    border-radius: 3px;
  }
  div::-webkit-scrollbar-thumb:hover {
    background: rgba(0,229,255,0.5);
  }
  .dm-member-btn:hover {
    background: rgba(255, 255, 255, 0.04) !important;
  }
</style>
