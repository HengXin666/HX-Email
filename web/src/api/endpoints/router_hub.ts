import type {
  RouterApiKey,
  RouterEvent,
  RouterEventPage,
  RouterHubStats,
  RouterIssuedKey,
  RouterSocketFrame,
  RouterSource,
  RouterSubscription,
  RouterSubscriptionCreate,
  RouterSubscriptionList,
  RouterSubscriptionUpdate,
  RouterWebhookDelivery,
  RouterWebhookPing,
} from "../../types/messaging";
import { API_BASE, request } from "../core";

const SUBS = "/router/subscriptions";

/** Parse one SSE block ("id: …\nevent: …\ndata: …") into its fields. */
export function parseSseBlock(block: string): { id: string; event: string; data: string } {
  let id = "";
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("id:")) id = line.slice(3).trim();
    else if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return { id, event, data: data.join("\n") };
}

/**
 * Follow a subscription over SSE. EventSource cannot send an Authorization header, so
 * this reads the stream with fetch; aborting the signal closes the connection.
 */
async function streamSubscription(
  id: number,
  onEvent: (event: RouterEvent) => void,
  signal: AbortSignal,
  autoAck = false,
): Promise<void> {
  const token = window.localStorage?.getItem("hx_token") ?? "";
  const res = await fetch(`${API_BASE}${SUBS}/${id}/stream?auto_ack=${autoAck}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.error?.message || err?.detail || `订阅流打开失败 (${res.status})`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let cut = buffer.indexOf("\n\n");
    while (cut >= 0) {
      const frame = parseSseBlock(buffer.slice(0, cut));
      buffer = buffer.slice(cut + 2);
      if (frame.event === "message" && frame.data) onEvent(JSON.parse(frame.data) as RouterEvent);
      cut = buffer.indexOf("\n\n");
    }
  }
}

/** ws(s):// URL of a subscription socket on the same origin as the console. */
export function socketUrl(
  id: number,
  autoAck: boolean,
  where: { protocol: string; host: string } = window.location,
): string {
  const scheme = where.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${where.host}${API_BASE}${SUBS}/${id}/ws?auto_ack=${autoAck}`;
}

export interface SubscriptionSocket {
  ack: (cursor: string) => void;
  close: () => void;
}

/**
 * Follow a subscription over WebSocket. Browsers cannot set Authorization on a socket,
 * so the token rides as the subprotocol "bearer.<token>" next to "hx-router".
 */
function openSubscriptionSocket(
  id: number,
  onFrame: (frame: RouterSocketFrame) => void,
  onClose: (code: number, reason: string) => void,
  autoAck = false,
): SubscriptionSocket {
  const token = window.localStorage?.getItem("hx_token") ?? "";
  const socket = new WebSocket(socketUrl(id, autoAck), ["hx-router", `bearer.${token}`]);
  socket.onmessage = (event: MessageEvent) => {
    try {
      onFrame(JSON.parse(String(event.data)) as RouterSocketFrame);
    } catch {
      // 非 JSON 帧不是本协议的, 忽略
    }
  };
  socket.onclose = (event: CloseEvent) => onClose(event.code, event.reason);
  return {
    ack: (cursor: string) => {
      if (socket.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify({ type: "ack", cursor }));
    },
    close: () => socket.close(),
  };
}

export const routerHubApi = {
  routerSources: (): Promise<{ sources: RouterSource[] }> =>
    request<{ sources: RouterSource[] }>("/router/sources"),

  routerHubStats: (): Promise<RouterHubStats> => request<RouterHubStats>("/router/hub"),

  listSubscriptions: (): Promise<RouterSubscriptionList> => request<RouterSubscriptionList>(SUBS),

  createSubscription: (body: RouterSubscriptionCreate): Promise<RouterSubscription> =>
    request<RouterSubscription>(SUBS, { method: "POST", body: JSON.stringify(body) }),

  updateSubscription: (id: number, body: RouterSubscriptionUpdate): Promise<RouterSubscription> =>
    request<RouterSubscription>(`${SUBS}/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  deleteSubscription: (id: number): Promise<{ id: number; deleted: boolean }> =>
    request<{ id: number; deleted: boolean }>(`${SUBS}/${id}`, { method: "DELETE" }),

  ackSubscription: (id: number, cursor: string): Promise<RouterSubscription> =>
    request<RouterSubscription>(`${SUBS}/${id}/ack`, {
      method: "POST",
      body: JSON.stringify({ cursor }),
    }),

  peekSubscription: (id: number, limit = 20): Promise<RouterEventPage> =>
    request<RouterEventPage>(`${SUBS}/${id}/events?timeout_seconds=0&limit=${limit}`),

  streamSubscription,

  openSubscriptionSocket,

  listWebhookDeliveries: (id: number): Promise<{ deliveries: RouterWebhookDelivery[] }> =>
    request<{ deliveries: RouterWebhookDelivery[] }>(`${SUBS}/${id}/deliveries`),

  redeliverWebhook: (id: number, deliveryId: string): Promise<{ status: string }> =>
    request<{ status: string }>(`${SUBS}/${id}/deliveries/${deliveryId}/redeliver`, {
      method: "POST",
    }),

  pingWebhook: (id: number): Promise<RouterWebhookPing> =>
    request<RouterWebhookPing>(`${SUBS}/${id}/webhook/ping`, { method: "POST" }),

  rotateWebhookSecret: (id: number): Promise<RouterSubscription> =>
    request<RouterSubscription>(`${SUBS}/${id}/webhook/rotate`, { method: "POST" }),

  listRouterKeys: (): Promise<{ keys: RouterApiKey[] }> =>
    request<{ keys: RouterApiKey[] }>("/router/api-keys"),

  createRouterKey: (name: string): Promise<RouterIssuedKey> =>
    request<RouterIssuedKey>("/router/api-keys", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  revokeRouterKey: (id: number): Promise<{ id: number; revoked: boolean }> =>
    request<{ id: number; revoked: boolean }>(`/router/api-keys/${id}`, { method: "DELETE" }),
};
