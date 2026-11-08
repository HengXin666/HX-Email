import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { parseSseBlock, socketUrl } from "../api/endpoints/router_hub";
import { ToastProvider } from "../components/ui/Toast";
import type { RouterSubscription } from "../types/messaging";
import {
  buildSnippets,
  describeDelivery,
  describeFilter,
  sourceChoices,
} from "./impl/subscription_snippets";
import { Subscriptions } from "./Subscriptions";

const subscription: RouterSubscription = {
  id: 7,
  name: "bot",
  source: "qq:1/group",
  address: "qq:1/group",
  filter: { direction: "inbound", kinds: [], exclude_self: true, mention_self: true, contains: "" },
  delivery: "pull",
  status: "active",
  ack_cursor: "c1",
  created_at: "2026-11-08 13:00:00",
  updated_at: "2026-11-08 13:00:00",
  expires_at: null,
  backlog: 3,
};

const hook: RouterSubscription = {
  ...subscription,
  id: 9,
  name: "hook",
  delivery: "webhook",
  webhook: { url: "https://agent.example/in", push_cursor: "c1.0.5" },
  backlog: 0,
};

const createSubscription = vi.fn();
const redeliverWebhook = vi.fn();
const pingWebhook = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    listSubscriptions: () => Promise.resolve({ subscriptions: [subscription, hook], limit: 50 }),
    routerSources: () =>
      Promise.resolve({
        sources: [
          {
            platform: "qq",
            instance_id: 1,
            address: "qq:1",
            name: "QQ",
            state: "online",
            outbound: "open",
          },
        ],
      }),
    routerHubStats: () => Promise.resolve({ waiting: 2, published: 9 }),
    listRouterKeys: () => Promise.resolve({ keys: [] }),
    createSubscription: (...args: unknown[]) => createSubscription(...args),
    listWebhookDeliveries: () =>
      Promise.resolve({
        deliveries: [
          {
            delivery_id: "d_4",
            status: "dead",
            attempts: 12,
            range: "m_1-m_3",
            messages: 3,
            next_attempt_at: "",
            last_error: "http_503",
            created_at: "",
            updated_at: "",
          },
        ],
      }),
    redeliverWebhook: (...args: unknown[]) => redeliverWebhook(...args),
    pingWebhook: (...args: unknown[]) => pingWebhook(...args),
  },
}));

beforeEach(() => {
  createSubscription.mockResolvedValue({ ...subscription, id: 8 });
  redeliverWebhook.mockResolvedValue({ status: "queued" });
  pingWebhook.mockResolvedValue({ ok: true, status_code: 204, error: "", elapsed_ms: 12 });
});

afterEach(() => {
  vi.clearAllMocks();
});

test("parses SSE frames the router stream emits", () => {
  expect(parseSseBlock('id: c9\ndata: {"text":"hi"}')).toEqual({
    id: "c9",
    event: "message",
    data: '{"text":"hi"}',
  });
  expect(parseSseBlock('event: ready\ndata: {"cursor":"c0"}').event).toBe("ready");
});

test("snippets carry the subscription id and the key", () => {
  const snippets = buildSnippets({
    baseUrl: "https://hx.example/api/v1",
    token: "hxr_abc",
    subscriptionId: 7,
    source: "qq:1/group",
  });
  const curl = snippets.find((item) => item.key === "curl")?.code ?? "";
  expect(curl).toContain("/router/subscriptions/7/events");
  expect(curl).toContain("Bearer hxr_abc");
  expect(snippets.find((item) => item.key === "mcp")?.code).toContain("https://hx.example/mcp");
  expect(describeFilter(subscription.filter)).toBe("入站 · 排除自己 · 仅 @我");
  expect(sourceChoices("qq", 1)).toContain("qq:1/group");
  const ws = snippets.find((item) => item.key === "websocket")?.code ?? "";
  expect(ws).toContain("wss://hx.example/api/v1/router/subscriptions/7/ws");
  expect(ws).toContain("bearer.hxr_abc");
  const receiver = buildSnippets({
    baseUrl: "https://hx.example/api/v1",
    token: "hxr_abc",
    subscriptionId: null,
    source: "qq:1/group",
    webhookSecret: "whsec_xyz",
  });
  expect(receiver.find((item) => item.key === "webhook")?.code).toContain('b"whsec_xyz"');
  expect(receiver.find((item) => item.key === "python")?.code).toContain(
    'json={"source": "qq:1/group"}).json()["id"]',
  );
  expect(describeDelivery(hook)).toBe("Webhook → https://agent.example/in");
  expect(socketUrl(7, true, { protocol: "https:", host: "hx.example" })).toBe(
    "wss://hx.example/api/v1/router/subscriptions/7/ws?auto_ack=true",
  );
});

test("webhook subscription shows its delivery log, pings and redelivers", async () => {
  render(
    <ToastProvider>
      <Subscriptions />
    </ToastProvider>,
  );
  fireEvent.click(await screen.findByText("#9 hook"));
  expect(await screen.findByTestId("webhook-panel")).toBeTruthy();
  expect(await screen.findByText("已放弃")).toBeTruthy();
  fireEvent.click(screen.getByText("重投"));
  await waitFor(() => expect(redeliverWebhook).toHaveBeenCalledWith(9, "d_4"));
  fireEvent.click(screen.getByText("测试推送"));
  expect((await screen.findByTestId("webhook-ping")).textContent).toContain("HTTP 204");
});

test("lists subscriptions with backlog and creates a new one", async () => {
  render(
    <ToastProvider>
      <Subscriptions />
    </ToastProvider>,
  );
  expect(await screen.findByText("#7 bot")).toBeTruthy();
  expect(screen.getByText(/积压 3/)).toBeTruthy();
  expect(screen.getByTestId("hub-stats").textContent).toContain("正在等待 2");
  fireEvent.click(screen.getByText("QQ · qq:1/private"));
  fireEvent.click(screen.getByText("创建订阅"));
  await waitFor(() =>
    expect(createSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ source: "qq:1/private", from: "now" }),
    ),
  );
});
