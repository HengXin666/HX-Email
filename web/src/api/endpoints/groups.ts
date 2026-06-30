import type { Group, Tag } from "../../types";
import { request } from "../core";

export const groupsApi = {
  createGroup: (name: string, color = "#58a6ff", proxy_url = "") =>
    request<Group>("/groups", {
      method: "POST",
      body: JSON.stringify({ name, color, proxy_url }),
    }),

  updateGroup: (id: number, name: string, color: string, proxy_url = "") =>
    request<Group>(`/groups/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name, color, proxy_url }),
    }),

  deleteGroup: (id: number) => request<void>(`/groups/${id}`, { method: "DELETE" }),

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
