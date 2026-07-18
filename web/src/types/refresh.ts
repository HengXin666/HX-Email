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
}
