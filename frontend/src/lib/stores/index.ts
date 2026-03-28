import { writable, derived } from "svelte/store";
import {
  fetchMission, fetchTasks, fetchDecisions, fetchTeam, fetchBlockers,
} from "../api";
import type {
  Mission, Task, Blocker, Decision, TeamMember, StatusPanel, StatusReport,
} from "../lib/api";

export const mission = writable<Mission | null>(null);
export const missions = writable<Mission[]>([]);
export const tasks = writable<Task[]>([]);
export const blockers = writable<Blocker[]>([]);
export const decisions = writable<Decision[]>([]);
export const team = writable<TeamMember[]>([]);
export const loading = writable(true);
export const error = writable<string | null>(null);

// Status stores
export const statusPanel = writable<StatusPanel | null>(null);
export const statusHistory = writable<StatusReport[]>([]);
export const statusHistoryLoading = writable(false);
export const statusDetailAgent = writable<string | null>(null);
export const showDifficultyModal = writable(false);
export const showHistorySidebar = writable(false);
export const showWorkbench = writable(true);

export const completedTasks = derived(tasks, ($tasks) =>
  $tasks.filter((t) => t.status === "completed")
);
export const pendingTasks = derived(tasks, ($tasks) =>
  $tasks.filter((t) => t.status === "pending")
);
export const openBlockers = derived(blockers, ($blockers) =>
  $blockers.filter((b) => b.status === "open")
);
export const pendingDecisions = derived(decisions, ($decisions) =>
  $decisions.filter((d) => d.decision_status === "pending")
);

// Status derived stores
export const agentsWithDifficulties = derived(statusPanel, ($panel) =>
  ($panel?.agents || []).filter((a) => a.difficulty && a.difficulty_level !== "none")
);
export const agentsNeedingDecision = derived(statusPanel, ($panel) =>
  ($panel?.agents || []).filter((a) => a.needs_decision)
);
export const staleAgents = derived(statusPanel, ($panel) =>
  ($panel?.agents || []).filter((a) => a.is_stale)
);

// Refresh all data stores from REST API
export async function fetchAll() {
  try {
    const [missionData, tasksData, decisionsData, teamData, blockersData] = await Promise.all([
      fetchMission(),
      fetchTasks(),
      fetchDecisions(),
      fetchTeam(),
      fetchBlockers(),
    ]);
    mission.set(missionData);
    tasks.set(tasksData);
    decisions.set(decisionsData);
    team.set(teamData);
    blockers.set(blockersData);
    loading.set(false);
  } catch (e) {
    console.error("Failed to fetch data:", e);
  }
}
