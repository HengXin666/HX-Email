import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { parseSseBlock } from "../api/endpoints/router_hub";
import { ToastProvider } from "../components/ui/Toast";
import type { RouterSubscription } from "../types/messaging";
import { buildSnippets, describeFilter, sourceChoices } from "./impl/subscription_snippets";
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

const createSubscription = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    listSubscriptions: () => Promise.resolve({ subscriptions: [subscription], limit: 50 }),
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
  },
}));

beforeEach(() => {
  createSubscription.mockResolvedValue({ ...subscription, id: 8 });
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
