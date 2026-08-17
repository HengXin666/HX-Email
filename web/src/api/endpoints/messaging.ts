import type {
  MessagingConversation,
  MessagingGroup,
  MessagingInstance,
  MessagingLoginProbe,
  MessagingLoginState,
  MessagingLoginTicket,
  MessagingMessage,
  MessagingPluginInfo,
} from "../../types/messaging";
import { request, requestBlob } from "../core";

export const messagingApi = {
  catalog: () =>
    request<{ plugins: MessagingPluginInfo[] }>("/messaging/catalog").then((r) => r.plugins),

  listInstances: () =>
    request<{ instances: MessagingInstance[] }>("/messaging/instances").then((r) => r.instances),

  createInstance: (data: { kind: string; name: string; config: Record<string, string> }) =>
    request<{ instance: MessagingInstance }>("/messaging/instances", {
      method: "POST",
      body: JSON.stringify(data),
    }).then((r) => r.instance),

  deleteInstance: (id: number) =>
    request<{ success: boolean }>(`/messaging/instances/${id}`, {
      method: "DELETE",
    }),

  connect: (id: number) =>
    request<{ status: Record<string, string> }>(`/messaging/instances/${id}/connect`, {
      method: "POST",
    }),

  disconnect: (id: number) =>
    request<{ success: boolean }>(`/messaging/instances/${id}/disconnect`, {
      method: "POST",
    }),

  getLogin: (id: number) =>
    request<{ login: MessagingLoginTicket }>(`/messaging/instances/${id}/login`, {
      method: "POST",
    }).then((r) => r.login),

  getLoginStatus: (id: number) =>
    request<{ login: MessagingLoginState }>(`/messaging/instances/${id}/login/status`, {
      method: "POST",
    }).then((r) => r.login),

  conversations: (id: number) =>
    request<{ conversations: MessagingConversation[] }>(
      `/messaging/instances/${id}/conversations`,
    ).then((r) => r.conversations),

  messages: (id: number, chatId: string, limit = 50) =>
    request<{ messages: MessagingMessage[] }>(
      `/messaging/instances/${id}/messages?chat_id=${encodeURIComponent(chatId)}&limit=${limit}`,
    ).then((r) => r.messages),

  sendMessage: (id: number, data: { chat_id: string; chat_type: string; text: string }) =>
    request<{ message_id: string }>(`/messaging/instances/${id}/send`, {
      method: "POST",
      body: JSON.stringify(data),
    }).then((r) => r.message_id),

  groups: (id: number) =>
    request<{ groups: MessagingGroup[] }>(`/messaging/instances/${id}/groups`).then(
      (r) => r.groups,
    ),

  groupAction: (
    id: number,
    groupId: string,
    data: { action: string; member_id?: string; duration_seconds?: number },
  ) =>
    request<{ applied: boolean }>(
      `/messaging/instances/${id}/groups/${encodeURIComponent(groupId)}/action`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  probeLogin: (id: number) =>
    request<{ probe: MessagingLoginProbe }>(`/messaging/instances/${id}/login/probe`, {
      method: "POST",
    }).then((r) => r.probe),

  updateConfig: (id: number, config: Record<string, string>) =>
    request<{ instance: MessagingInstance }>(`/messaging/instances/${id}/config`, {
      method: "PUT",
      body: JSON.stringify({ config }),
    }).then((r) => r.instance),

  engineStart: (id: number) =>
    request<{ pid: number; instance: MessagingInstance }>(
      `/messaging/instances/${id}/engine/start`,
      { method: "POST" },
    ).then((r) => r),

  engineStop: (id: number) =>
    request<{ success: boolean }>(`/messaging/instances/${id}/engine/stop`, {
      method: "POST",
    }),

  engineRefreshQr: (id: number) =>
    request<{ success: boolean }>(`/messaging/instances/${id}/engine/refresh-qr`, {
      method: "POST",
    }),

  qrBlob: (id: number) => requestBlob(`/messaging/instances/${id}/login/qr`).then((blob) => blob),
};
