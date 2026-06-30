import type { Platform, PlatformBinding } from "../../types";
import { request } from "../core";

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
};
