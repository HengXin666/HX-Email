import { request } from "../core";

export const settingsApi = {
  getSettings: () => request<Record<string, string>>("/settings"),

  updateSettings: (data: Record<string, unknown>) =>
    request<Record<string, string>>("/settings", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  testTelegram: (data: Record<string, unknown>) =>
    request<{ success: boolean; message: string }>("/settings/telegram-test", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  testEmail: (data: Record<string, unknown>) =>
    request<{ success: boolean; message?: string; error?: string }>("/settings/email-test", {
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
    request<{ success: boolean; domains?: string[]; default_domain?: string; message?: string }>(
      "/settings/cf-worker-sync-domains",
      { method: "POST", body: JSON.stringify(data) },
    ),

  getAPIKeyPlaintext: () =>
    request<{ external_api_key: string }>("/settings/external-api-key/plaintext"),

  rotateExternalAPIKey: () =>
    request<{ external_api_key: string }>("/settings/external-api-key/rotate", {
      method: "POST",
    }),

  testScript: (path: string, timeoutSeconds: number) =>
    request<{ success: boolean; message: string }>("/settings/script-test", {
      method: "POST",
      body: JSON.stringify({ path, timeout_seconds: timeoutSeconds }),
    }),

  getRuntimeStatus: () =>
    request<{
      polling: {
        running: boolean;
        enabled: boolean;
        interval_seconds: number;
        last_run: string;
        next_run: string;
        last_error: string;
      };
      deliveries: {
        pending: number;
        sending: number;
        sent: number;
        failed: number;
        skipped: number;
        last_error: string;
        last_error_at: string;
      };
      pool: {
        enabled: boolean;
        api_key_configured: boolean;
        total: number;
        available: number;
        claimed: number;
      };
    }>("/settings/runtime-status"),

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
};
