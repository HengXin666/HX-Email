import { beforeEach, expect, test, vi } from "vitest";

import type { SSERefreshEvent } from "../types";
import { requestBlob, streamRefresh } from "./core";

beforeEach(() => {
  window.localStorage.setItem("hx_token", "test-token");
  vi.restoreAllMocks();
});

test("streamRefresh preserves SSE event types through a chunked complete event", async () => {
  const encoder: TextEncoder = new TextEncoder();
  const chunks: string[] = [
    'event: start\ndata: {"total":7}\n\nevent: progress\ndata: {"current":1,',
    '"total":7,"email":"one@example.com","success":true}\n\nevent: progress\n',
    'data: {"current":3,"total":7,"email":"three@example.com","success":true}\n\n',
    'event: complete\ndata: {"total":7,"success":7,"failed":0}',
  ];
  const body: ReadableStream<Uint8Array> = new ReadableStream({
    start(controller: ReadableStreamDefaultController<Uint8Array>): void {
      chunks.forEach((chunk: string) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
  );
  const events: SSERefreshEvent[] = [];

  await streamRefresh("/email-accounts/refresh-all", undefined, (event: SSERefreshEvent) => {
    events.push(event);
  });

  expect(events).toEqual([
    { type: "start", total: 7 },
    {
      type: "progress",
      current: 1,
      total: 7,
      email: "one@example.com",
      success: true,
    },
    {
      type: "progress",
      current: 3,
      total: 7,
      email: "three@example.com",
      success: true,
    },
    { type: "complete", total: 7, success: 7, failed: 0 },
  ]);
});

test("requestBlob sends the bearer token and returns binary content", async () => {
  const backupBlob: Blob = new Blob(["backup"], { type: "application/zip" });
  const response: Response = {
    blob: vi.fn().mockResolvedValue(backupBlob),
    ok: true,
    status: 200,
  } as unknown as Response;
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response);

  const backup: Blob = await requestBlob("/admin/backup/export");

  expect(backup).toBe(backupBlob);
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/admin/backup/export",
    expect.objectContaining({
      headers: { Authorization: "Bearer test-token" },
    }),
  );
});
