import { request } from "../core";

export const settingsApi = {
  getSettings: () => request<Record<string, string>>("/settings"),

  updateSettings: (data: Record<string, unknown>) =>
    request<{ success: boolean }>("/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  validateCron: (cron: string) =>
    request<{ valid: boolean; message: string }>("/settings/validate-cron", {
      method: "POST",
      body: JSON.stringify({ cron_expression: cron }),
    }),

  testTelegram: (data: Record<string, unknown>) =>
    request<{ success: boolean; message: string }>("/settings/telegram-test", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  testEmail: (data: Record<string, unknown>) =>
    request<{ success: boolean; message: string }>("/settings/email-test", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  testWebhook: (data: Record<string, unknown>) =>
    request<{ success: boolean; message: string }>("/settings/webhook-test", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  testVerificationAI: (data: Record<string, unknown>) =>
    request<{ success: boolean; code: string; message: string }>("/settings/verification-ai-test", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  syncCFDomains: (data: Record<string, unknown>) =>
    request<{ success: boolean; domains: string[]; message: string }>(
      "/settings/cf-worker-sync-domains",
      { method: "POST", body: JSON.stringify(data) },
    ),

  getAPIKeyPlaintext: () =>
    request<{ external_api_key: string }>("/settings/external-api-key/plaintext"),

  getVersionCheck: () =>
    request<{
      version?: string;
      current_version: string;
      latest_version?: string;
      has_update: boolean;
      repository_url?: string;
    }>("/system/version-check"),

  getUpdateAnnouncement: () =>
    request<{
      success: boolean;
      source: string;
      current_version: string;
      latest_version: string;
      has_update: boolean;
      title: string;
      body: string;
      html_url: string;
      published_at: string;
      repository_url: string;
    }>("/system/update-announcement"),

  getDeploymentInfo: () =>
    request<{ python_version: string; platform: string }>("/system/deployment-info"),

  triggerUpdate: () =>
    request<{ success: boolean; message: string }>("/system/trigger-update", {
      method: "POST",
    }),

  testWatchtower: () =>
    request<{ success: boolean; message: string }>("/system/test-watchtower", {
      method: "POST",
    }),

  reloadPlugins: () =>
    request<{ success: boolean; message: string }>("/system/reload-plugins", {
      method: "POST",
    }),
};
