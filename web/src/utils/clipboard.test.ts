import { afterEach, expect, test, vi } from "vitest";

import { copyToClipboard } from "./clipboard";

const originalClipboard = navigator.clipboard;
const originalExecCommand = document.execCommand;

afterEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: originalClipboard,
  });
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: originalExecCommand,
  });
  vi.restoreAllMocks();
});

test("copyToClipboard falls back when clipboard write is unavailable", async () => {
  const writeText = vi.fn(async () => {
    throw new Error("denied");
  });
  const execCommand = vi.fn(() => true);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: execCommand,
  });

  const copied = await copyToClipboard("123456");

  expect(copied).toBe(true);
  expect(writeText).toHaveBeenCalledWith("123456");
  expect(execCommand).toHaveBeenCalledWith("copy");
});
