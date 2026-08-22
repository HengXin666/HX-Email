export interface RefreshLog {
  id: number;
  account_id: number;
  email: string;
  status: "pending" | "success" | "failed";
  message: string;
  error_detail: string;
  started_at: string;
  completed_at: string;
  created_at: string;
}

export interface InvalidTokenCandidate {
  account_id: number;
  email: string;
  error_detail: string;
  last_failed_at: string;
}

export interface RefreshStats {
  total: number;
  success: number;
  failed: number;
  pending: number;
  last_refresh: string;
}

export interface SSERefreshEvent {
  type: "start" | "progress" | "complete";
  current?: number;
  total?: number;
  email?: string;
  status?: string;
  success?: boolean | number;
  failed?: number;
  stopped?: boolean;
  error?: string;
}

type PatrolStatus =
  | "idle"
  | "starting"
  | "running"
  | "paused"
  | "stopping"
  | "done"
  | "error"
  | "stopped";

export interface PatrolSnapshot {
  status: PatrolStatus;
  mode: string;
  mode_label: string;
  group_id: number | null;
  total: number;
  current: number;
  success: number;
  failed: number;
  email: string;
  started_at: string | null;
  finished_at: string | null;
  error: string;
}

export type PatrolStreamEvent = ({ type: "status" } & PatrolSnapshot) | SSERefreshEvent;
