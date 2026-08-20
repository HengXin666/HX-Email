import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ToastProvider } from "../../components/ui/Toast";
import type { PlatformRule, PlatformScanItem } from "../../types";
import { PlatformRecognitionModal } from "./PlatformRecognitionModal";

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({
      children,
      animate: _animate,
      exit: _exit,
      initial: _initial,
      transition: _transition,
      ...props
    }: React.HTMLAttributes<HTMLDivElement> & Record<string, unknown>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

const listRules = vi.fn();
const createRule = vi.fn();
const deleteRule = vi.fn();
const scanPlatforms = vi.fn();
const acceptScan = vi.fn();
const onAccepted = vi.fn();

vi.mock("../../api/client", () => ({
  api: {
    listRules: (...args: unknown[]) => listRules(...args),
    createRule: (...args: unknown[]) => createRule(...args),
    deleteRule: (...args: unknown[]) => deleteRule(...args),
    scanPlatforms: (...args: unknown[]) => scanPlatforms(...args),
    acceptScan: (...args: unknown[]) => acceptScan(...args),
  },
}));

const existingRule: PlatformRule = {
  id: 1,
  user_id: 1,
  name: "GitHub 通知",
  match_field: "domain",
  match_type: "contains",
  pattern: "github.com",
  platform_name: "GitHub",
  enabled: true,
};

const scanItem: PlatformScanItem = {
  platform: "github.com",
  source: "domain",
  senders: ["noreply@github.com"],
  sender_count: 1,
  message_count: 3,
  usable_email_ids: [10],
  first_seen: "2026-08-01 10:00:00",
  last_seen: "2026-08-02 10:00:00",
};

function renderModal(): void {
  render(
    <ToastProvider>
      <PlatformRecognitionModal open onClose={() => undefined} onAccepted={onAccepted} />
    </ToastProvider>,
  );
}

beforeEach(() => {
  listRules.mockResolvedValue([existingRule]);
  createRule.mockResolvedValue({ ...existingRule, id: 2 });
  deleteRule.mockResolvedValue(undefined);
  scanPlatforms.mockResolvedValue([scanItem]);
  acceptScan.mockResolvedValue({
    platform: "github.com",
    platform_id: 99,
    bindings_created: 1,
    bindings_skipped: 0,
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

test("rules tab lists existing rules and can create a new one", async () => {
  renderModal();

  await screen.findByText("GitHub");
  fireEvent.click(screen.getByRole("button", { name: /添加规则/ }));

  fireEvent.change(screen.getByLabelText("规则名称"), { target: { value: "Google 验证码" } });
  fireEvent.change(screen.getByLabelText("目标平台"), { target: { value: "Google" } });
  fireEvent.change(screen.getByLabelText("匹配模式"), { target: { value: "google.com" } });
  fireEvent.click(screen.getByRole("button", { name: "创建规则" }));

  await waitFor(() => {
    expect(createRule).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Google 验证码",
        platform_name: "Google",
        pattern: "google.com",
        match_field: "domain",
      }),
    );
  });
});

test("scan tab runs recognition and accepts a candidate into platforms", async () => {
  renderModal();

  fireEvent.click(screen.getByRole("button", { name: "一键识别" }));
  fireEvent.click(await screen.findByRole("button", { name: /识别历史邮件/ }));

  await screen.findByText("github.com");
  expect(screen.getByText("3 封邮件 · 1 个发件人")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "纳入平台" }));

  await waitFor(() => {
    expect(acceptScan).toHaveBeenCalledWith("github.com", [10]);
    expect(onAccepted).toHaveBeenCalled();
  });
});

test("scan with no results shows a hint instead of a list", async () => {
  scanPlatforms.mockResolvedValue([]);
  renderModal();

  fireEvent.click(screen.getByRole("button", { name: "一键识别" }));
  fireEvent.click(await screen.findByRole("button", { name: /识别历史邮件/ }));

  await screen.findByText(/未识别到平台/);
});
