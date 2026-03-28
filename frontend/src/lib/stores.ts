import { writable } from "svelte/store";

// ─── 数据 ────────────────────────────────────────────────────────────
export const tasks = writable<any[]>([]);
export const missions = writable<any[]>([]);
export const decisions = writable<any[]>([]);
export const team = writable<any[]>([]);
export const loading = writable(false);

// ─── 导航 ────────────────────────────────────────────────────────────
export const mission = writable<string>("");
export const showWorkbench = writable<boolean>(false);

// ─── 待决策 ──────────────────────────────────────────────────────────
export const pendingDecisions = writable<any[]>([]);

// ─── 弹窗 ────────────────────────────────────────────────────────────
export const showDifficultyModal = writable<boolean>(false);
export const showHistorySidebar = writable<boolean>(false);
export const statusDetailAgent = writable<string | null>(null);
export const statusHistory = writable<any[]>([]);
export const statusHistoryLoading = writable<boolean>(false);

// ─── 数据加载 ────────────────────────────────────────────────────────
export async function fetchAll() {
  loading.set(true);
  try {
    const [tasksRes, missionsRes, decisionsRes] = await Promise.all([
      fetch("/api/tasks").then(r => r.json()),
      fetch("/api/missions").then(r => r.json()),
      fetch("/api/decisions").then(r => r.json()),
    ]);
    tasks.set(tasksRes);
    missions.set(missionsRes);
    decisions.set(decisionsRes);
  } catch (e) {
    console.error("Failed to fetch data:", e);
  } finally {
    loading.set(false);
  }
}
