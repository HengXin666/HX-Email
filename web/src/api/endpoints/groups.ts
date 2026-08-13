import type { Group, Tag } from "../../types";
import { request } from "../core";

export const groupsApi = {
  createGroup: (
    name: string,
    color = "#58a6ff",
    proxy_url = "",
    notify_enabled?: boolean,
    polling_enabled?: boolean,
  ) =>
    request<Group>("/groups", {
      method: "POST",
      body: JSON.stringify({ name, color, proxy_url, notify_enabled, polling_enabled }),
    }),

  updateGroup: (
    id: number,
    name: string,
    color: string,
    proxy_url = "",
    notify_enabled?: boolean,
    polling_enabled?: boolean,
  ) =>
    request<Group>(`/groups/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name, color, proxy_url, notify_enabled, polling_enabled }),
    }),

  deleteGroup: (id: number) => request<void>(`/groups/${id}`, { method: "DELETE" }),

  toggleGroupNotify: (id: number, enabled: boolean) =>
    request<{ id: number; notify_enabled: boolean }>(`/groups/${id}/notify`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),

  toggleGroupPolling: (id: number, enabled: boolean) =>
    request<{ id: number; polling_enabled: boolean }>(`/groups/${id}/polling`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),

  listGroups: () => request<Group[]>("/groups"),

  testProxy: (proxy_url: string) =>
    request<{ success: boolean; latency_ms: number; message: string }>("/groups/proxy-test", {
      method: "POST",
      body: JSON.stringify({ proxy_url }),
    }),

  createTag: (name: string, color = "#238636") =>
    request<Tag>("/tags", {
      method: "POST",
      body: JSON.stringify({ name, color }),
    }),

  listTags: () => request<Tag[]>("/tags"),
};
