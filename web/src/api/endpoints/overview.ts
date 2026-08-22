import type {
  AccountStats,
  ActivityStats,
  LatestMailMessage,
  MailNotification,
  Overview,
  OverviewSummary,
  PoolStats,
  VerificationStats,
} from "../../types";
import { request } from "../core";

export const overviewApi = {
  overview: () => request<Overview>("/workbench/overview"),

  getOverviewSummary: () => request<OverviewSummary>("/overview/summary"),

  getVerificationStats: () => request<VerificationStats>("/overview/verification-stats"),

  getPoolStats: () => request<PoolStats>("/overview/pool-stats"),

  getActivityStats: () => request<ActivityStats>("/overview/activity"),

  getAccountStats: (provider?: string) =>
    request<AccountStats>(
      provider
        ? `/overview/account-stats?provider=${encodeURIComponent(provider)}`
        : "/overview/account-stats",
    ),

  getLatestMessages: (limit = 20) =>
    request<{ messages: LatestMailMessage[] }>(`/overview/latest-messages?limit=${limit}`).then(
      (result) => result.messages,
    ),

  pollNotifications: (sinceId: number) =>
    request<{ latest_id: number; notifications: MailNotification[] }>(
      `/notifications?since_id=${sinceId}`,
    ),

  exportData: () => request<unknown>("/data/export"),

  importData: (data: unknown) =>
    request<unknown>("/data/import", { method: "POST", body: JSON.stringify(data) }),
};
