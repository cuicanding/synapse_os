import { writable, type Writable } from "svelte/store";
import type { StatusPanel, StatusReport } from "./api";

export const statusWsConnected: Writable<boolean> = writable(false);
export const statusPanel: Writable<StatusPanel | null> = writable(null);
export const statusEvents: Writable<StatusReport | null> = writable(null);
export const statusMdData: Writable<any | null> = writable(null);
export const taskActionRequired: Writable<any | null> = writable(null);
export const taskCompleted: Writable<any | null> = writable(null);

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectDelay = 1000;

function getWsUrl(): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const host = location.host;
  return `${protocol}//${host}/ws/status`;
}

function connect(): void {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  ws = new WebSocket(getWsUrl());

  ws.onopen = () => {
    console.log("[ws:status] connected");
    statusWsConnected.set(true);
    reconnectDelay = 1000;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "status_updated" || msg.type === "difficulty_reported" || msg.type === "decision_requested") {
        if (msg.payload?.panel) {
          statusPanel.set(msg.payload.panel as StatusPanel);
        }
        if (msg.payload?.report) {
          statusEvents.set(msg.payload.report as StatusReport);
        }
      }
      if (msg.type === "status_md_updated" && msg.payload) {
        statusMdData.set(msg.payload);
      }
      if (msg.type === "task_action_required") {
        taskActionRequired.set(msg.payload);
      }
      if (msg.type === "task_completed") {
        taskCompleted.set(msg.payload);
      }
    } catch (e) {
      console.error("[ws:status] parse error", e);
    }
  };

  ws.onclose = () => {
    console.log("[ws:status] disconnected, reconnecting in", reconnectDelay, "ms");
    statusWsConnected.set(false);
    reconnectTimer = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 1.5, 10000);
      connect();
    }, reconnectDelay);
  };

  ws.onerror = (err) => {
    console.error("[ws:status] error", err);
    ws?.close();
  };
}

export function startStatusWs(): void {
  connect();
}

export function stopStatusWs(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  ws?.close();
  ws = null;
}

export function reconnect(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  ws?.close();
  ws = null;
  reconnectDelay = 1000;
  connect();
}
