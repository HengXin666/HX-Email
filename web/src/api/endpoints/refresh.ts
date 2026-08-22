import type { InvalidTokenCandidate, PatrolSnapshot, RefreshLog, RefreshStats } from "../../types";
import { request } from "../core";

export const refreshApi = {
  refreshAccount: (id: number) =>
    request<{
      success: boolean;
      message: string;
      account_id: number;
      email: string;
      status?: string;
    }>(`/email-accounts/${id}/refresh`, { method: "POST" }),

  retryRefreshAccount: (id: number) =>
    request<{ success: boolean; message: string }>(`/email-accounts/${id}/retry-refresh`, {
      method: "POST",
    }),

  getRefreshLogs: (limit = 200, offset = 0) =>
    request<{ logs: RefreshLog[]; total: number }>(
      `/email-accounts/refresh-logs?limit=${limit}&offset=${offset}`,
    ),

  getAccountRefreshLogs: (id: number, limit = 100, offset = 0) =>
    request<{ logs: RefreshLog[] }>(
      `/email-accounts/${id}/refresh-logs?limit=${limit}&offset=${offset}`,
    ),

  getFailedRefreshLogs: () =>
    request<{ logs: RefreshLog[] }>("/email-accounts/refresh-logs/failed"),

  getInvalidTokenCandidates: (limit = 50, offset = 0) =>
    request<{ candidates: InvalidTokenCandidate[] }>(
      `/email-accounts/invalid-token-candidates?limit=${limit}&offset=${offset}`,
    ),

  getRefreshStats: () => request<RefreshStats>("/email-accounts/refresh-stats"),

  // ===== 持久化巡检 (后台线程, 刷新/切页不丢, 可暂停/恢复/终止) =====
  patrolStart: (payload: {
    mode: "all" | "failed" | "group" | "ungrouped" | "selected";
    group_id?: number;
    account_ids?: number[];
  }) =>
    request<{ success: boolean; snapshot: PatrolSnapshot }>("/email-accounts/patrol/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  patrolStatus: () => request<PatrolSnapshot>("/email-accounts/patrol/status"),

  patrolPause: () =>
    request<{ success: boolean; snapshot: PatrolSnapshot }>("/email-accounts/patrol/pause", {
      method: "POST",
    }),

  patrolResume: () =>
    request<{ success: boolean; snapshot: PatrolSnapshot }>("/email-accounts/patrol/resume", {
      method: "POST",
    }),

  patrolStop: () =>
    request<{ success: boolean; snapshot: PatrolSnapshot }>("/email-accounts/patrol/stop", {
      method: "POST",
    }),
};
