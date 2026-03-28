const BASE = "";

// 全局 401 处理：触发登录状态重置
function checkUnauthorized(r: Response) {
  if (r.status === 401) {
    window.dispatchEvent(new CustomEvent("synapse-unauthorized"));
  }
  return r;
}

async function apiFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const r = await fetch(input, init);
  checkUnauthorized(r);
  return r;
}

export interface Mission {
  id: string;
  title: string;
  status: string;
  priority: string;
  created_at: string;
  content?: string;
  description?: string;
  goals?: { title: string; detail: string }[];
  team_overview?: { role: string; member: string; duty: string }[];
  milestones?: { id: string; title: string; status: string }[];
  task_ids?: string[];
}

export interface Task {
  id: string;
  title: string;
  status: string;
  assignee: string;
  priority: string;
  created_at: string;
  content?: string;
  mission_id?: string;
  mission_title?: string;
  decision_status?: string;
  decision_detail?: string;
  has_blocker?: boolean;
  blocker_reason?: string;
  source_type?: string;
  creator?: string;
  domain?: string;
  task_content?: string;
  proposal_content?: string;
  judgment?: string;
}

export interface Blocker {
  id: string;
  title: string;
  status: string;
  priority: string;
  assignee: string;
  created_at: string;
  content?: string;
  reason?: string;
  task_id?: string;
  task_title?: string;
  mission_id?: string;
}

export interface Decision {
  id: string;
  title: string;
  status: string;
  priority: string;
  assignee: string;
  created_at: string;
  content?: string;
  decision_status?: string;
  decision_detail?: string;
  source_of_truth?: string;
  task_id?: string;
  task_title?: string;
  mission_id?: string;
  task_content?: string;
  proposal_content?: string;
  judgment_content?: string;
}

export interface TeamMember {
  id: string;
  name: string;
  role: string;
  status: string;
  avatar?: string;
  current_tasks?: { id: string; title: string; status: string }[];
  domain?: string;
}

export async function fetchMission(): Promise<Mission> {
  const r = await apiFetch(`${BASE}/api/mission`);
  return r.json();
}

export async function fetchTasks(): Promise<Task[]> {
  const r = await apiFetch(`${BASE}/api/tasks`);
  return r.json();
}

export async function fetchBlockers(): Promise<Blocker[]> {
  const r = await apiFetch(`${BASE}/api/blockers`);
  return r.json();
}

export async function fetchDecisions(): Promise<Decision[]> {
  const r = await apiFetch(`${BASE}/api/decisions`);
  return r.json();
}

export async function fetchTeam(): Promise<TeamMember[]> {
  const r = await apiFetch(`${BASE}/api/team`);
  return r.json();
}

// ─── Status API ─────────────────────────────────────────────────────────
export interface StatusReport {
  report_id: string;
  agent_id: string;
  agent_name: string;
  role: string;
  domain: string;
  current_task: string;
  progress: string;
  progress_detail: string;
  difficulty: string | null;
  difficulty_level: "none" | "minor" | "blocking";
  needs_decision: string | null;
  needs_help: string | null;
  task_id: string;
  type: "report" | "difficulty" | "decision";
  created_at: string;
}

export interface AgentStatus {
  agent_id: string;
  agent_name: string;
  role: string;
  domain: string;
  current_task: string;
  progress: string;
  progress_detail: string;
  difficulty: string | null;
  difficulty_level: "none" | "minor" | "blocking";
  needs_decision: string | null;
  needs_help: string | null;
  task_id: string;
  last_report_at: string;
  next_report_at: string;
  online_status: string;
  is_stale: boolean;
}

export interface StatusPanel {
  updated_at: string;
  agents: AgentStatus[];
  stale_threshold_minutes: number;
}

export interface StatusHistoryResponse {
  total: number;
  page: number;
  limit: number;
  records: StatusReport[];
}

export async function fetchStatusPanel(): Promise<StatusPanel> {
  const r = await apiFetch(`${BASE}/api/status/panel`);
  return r.json();
}

export async function postStatusReport(data: Partial<StatusReport>): Promise<{ success: boolean; report_id: string }> {
  const r = await apiFetch(`${BASE}/api/status/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return r.json();
}

export async function fetchStatusHistory(params?: {
  agent_id?: string;
  type?: string;
  task_id?: string;
  page?: number;
  limit?: number;
}): Promise<StatusHistoryResponse> {
  const qs = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) qs.set(k, String(v));
    }
  }
  const r = await apiFetch(`${BASE}/api/status/history?${qs}`);
  return r.json();
}

// ─── Task Action APIs ───────────────────────────────────────────────────
export interface TaskActionResponse {
  success: boolean;
  task_id: string;
  new_status: string;
  action: string;
  error?: string;
}

export async function approveTask(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/approve`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}

export async function rejectTask(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/reject`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}

export async function discussTask(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/discuss`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}

export async function acceptTask(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/accept`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}

export async function requestTaskRevision(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/request-revision`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}

// ─── Phase APIs ───────────────────────────────────────────────────────────
export interface PhaseInfo {
  id: string;
  label: string;
  status: string;
  assignee?: string;
  comment?: string;
  artifacts?: { name: string; path: string }[];
  discussions?: { time: string; sender: string; message: string }[];
}

export async function fetchTaskPhases(taskId: string): Promise<PhaseInfo[]> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/phases`);
  return r.json();
}

export async function phaseStart(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/phase/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}

export async function phaseSubmit(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/phase/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}

export async function phaseApprove(taskId: string, comment?: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/phase/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment }),
  });
  return r.json();
}

export async function phaseReject(taskId: string, reason: string, escalate: boolean): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/phase/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason, escalate }),
  });
  return r.json();
}

export async function phaseResubmit(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/phase/resubmit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}

export async function phaseTerminate(taskId: string, reason: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/phase/terminate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  return r.json();
}

export async function phaseDiscuss(taskId: string, action: string, message: string, sender: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/phase/discuss`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, message, sender }),
  });
  return r.json();
}

// ─── File Content API ─────────────────────────────────────────────────────
export async function fetchFileContent(path: string): Promise<{ content: string; error?: string }> {
  const r = await apiFetch(`${BASE}/api/file-content?path=${encodeURIComponent(path)}`);
  return r.json();
}

// ─── Artifact API ──────────────────────────────────────────────────────────
export async function addArtifact(taskId: string, artifact: { name: string; path: string; type: string }): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/artifacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(artifact),
  });
  return r.json();
}

// ─── Additional Task Actions ───────────────────────────────────────────────
export async function archiveTask(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/archive`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}

export async function completeTask(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/complete`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}

export async function abandonTask(taskId: string): Promise<TaskActionResponse> {
  const r = await apiFetch(`${BASE}/api/tasks/${taskId}/abandon`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return r.json();
}
