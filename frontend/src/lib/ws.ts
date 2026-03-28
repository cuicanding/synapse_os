import { writable, type Writable } from "svelte/store";

export type SynapseData = {
  mission: unknown;
  missions: unknown[];
  tasks: unknown[];
  blockers: unknown[];
  decisions: unknown[];
  team: unknown[];
};

export const wsConnected: Writable<boolean> = writable(false);
export const synapseData: Writable<SynapseData | null> = writable(null);
export const lastUpdated: Writable<string | null> = writable(null);

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectDelay = 1000;

function getWsUrl(): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const host = location.host;
  // In dev, proxy handles /ws → backend; in prod, same host
  return `${protocol}//${host}/ws`;
}

function connect(): void {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  ws = new WebSocket(getWsUrl());

  ws.onopen = () => {
    console.log("[ws] connected");
    wsConnected.set(true);
    reconnectDelay = 1000;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "data_updated") {
        synapseData.set(msg.payload as SynapseData);
        lastUpdated.set(msg.timestamp);
      } else if (msg.type === "heartbeat") {
        lastUpdated.set(msg.timestamp);
      }
    } catch (e) {
      console.error("[ws] parse error", e);
    }
  };

  ws.onclose = () => {
    console.log("[ws] disconnected, reconnecting in", reconnectDelay, "ms");
    wsConnected.set(false);
    reconnectTimer = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 1.5, 10000);
      connect();
    }, reconnectDelay);
  };

  ws.onerror = (err) => {
    console.error("[ws] error", err);
    ws?.close();
  };
}

export function startWs(): void {
  connect();
}

export function stopWs(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  ws?.close();
  ws = null;
}
