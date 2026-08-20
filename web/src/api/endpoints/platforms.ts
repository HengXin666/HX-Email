import type {
  AnalyzeEmailResult,
  Platform,
  PlatformBinding,
  PlatformRule,
  PlatformScanItem,
  RuleMatchField,
  RuleMatchType,
  ScanAcceptResult,
} from "../../types";
import { request } from "../core";

export interface PlatformRuleInput {
  name: string;
  match_field: RuleMatchField;
  match_type: RuleMatchType;
  pattern: string;
  platform_name: string;
  enabled: boolean;
}

export const platformsApi = {
  listPlatforms: () => request<{ platforms: Platform[] }>("/platforms").then((r) => r.platforms),

  createPlatform: (name: string) =>
    request<Platform>("/platforms", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  updatePlatform: (id: number, name: string) =>
    request<Platform>(`/platforms/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name }),
    }),

  deletePlatform: (id: number) => request<void>(`/platforms/${id}`, { method: "DELETE" }),

  listBindings: (emailId: number) =>
    request<{ platform_bindings: PlatformBinding[] }>(
      `/usable-emails/${emailId}/platform-bindings`,
    ).then((r) => r.platform_bindings),

  createBinding: (emailId: number, platform_id: number, status = "active", notes = "") =>
    request<PlatformBinding>(`/usable-emails/${emailId}/platform-bindings`, {
      method: "POST",
      body: JSON.stringify({ platform_id, status, notes }),
    }),

  updateBinding: (id: number, status: string, notes: string) =>
    request<PlatformBinding>(`/platform-bindings/${id}`, {
      method: "PUT",
      body: JSON.stringify({ status, notes }),
    }),

  listRules: () => request<{ rules: PlatformRule[] }>("/platform-rules").then((r) => r.rules),

  createRule: (rule: PlatformRuleInput) =>
    request<PlatformRule>("/platform-rules", {
      method: "POST",
      body: JSON.stringify(rule),
    }),

  updateRule: (id: number, rule: PlatformRuleInput) =>
    request<PlatformRule>(`/platform-rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(rule),
    }),

  deleteRule: (id: number) => request<void>(`/platform-rules/${id}`, { method: "DELETE" }),

  scanPlatforms: () =>
    request<{ items: PlatformScanItem[] }>("/platforms/scan", { method: "POST" }).then(
      (r) => r.items,
    ),

  acceptScan: (platform: string, usableEmailIds: number[]) =>
    request<ScanAcceptResult>("/platforms/scan/accept", {
      method: "POST",
      body: JSON.stringify({ platform, usable_email_ids: usableEmailIds }),
    }),

  analyzeEmailPlatforms: (emailId: number) =>
    request<{ results: AnalyzeEmailResult[] }>(`/usable-emails/${emailId}/platforms/analyze`, {
      method: "POST",
    }).then((r) => r.results),
};
