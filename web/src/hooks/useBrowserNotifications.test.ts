import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { MailNotification } from "../types";
import {
  isBrowserNotifyEnabled,
  pollOnce,
  setBrowserNotifyEnabled,
} from "./useBrowserNotifications";

const pollNotifications = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    pollNotifications: (...args: unknown[]) => pollNotifications(...args),
  },
}));

const notificationInstances: Array<{ title: string; options?: NotificationOptions }> = [];

class FakeNotification {
  static permission = "granted";
  onclick: (() => void) | null = null;
  constructor(title: string, options?: NotificationOptions) {
    notificationInstances.push({ title, options });
  }
  close(): void {}
}

function mailItem(id: number, code: string | null): MailNotification {
  return {
    id,
    usable_email_id: 1,
    address: "a@example.com",
    from_address: "noreply@site.com",
    subject: "Login code",
    verification_code: code,
    received_at: "2026-07-26T10:00:00Z",
  };
}

beforeEach(() => {
  window.localStorage.clear();
  notificationInstances.length = 0;
  FakeNotification.permission = "granted";
  vi.stubGlobal("Notification", FakeNotification);
  setBrowserNotifyEnabled(true);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

test("enable flag round-trips through localStorage", () => {
  setBrowserNotifyEnabled(false);
  expect(isBrowserNotifyEnabled()).toBe(false);
  setBrowserNotifyEnabled(true);
  expect(isBrowserNotifyEnabled()).toBe(true);
});

test("first poll initializes the cursor with since_id=-1 and shows nothing", async () => {
  pollNotifications.mockResolvedValue({ latest_id: 42, notifications: [] });

  await pollOnce();

  expect(pollNotifications).toHaveBeenCalledWith(-1);
  expect(window.localStorage.getItem("hx_notify_since_id")).toBe("42");
  expect(notificationInstances).toHaveLength(0);
});

test("subsequent polls notify new mail with the verification code and advance the cursor", async () => {
  window.localStorage.setItem("hx_notify_since_id", "42");
  pollNotifications.mockResolvedValue({
    latest_id: 44,
    notifications: [mailItem(43, "482913"), mailItem(44, null)],
  });

  await pollOnce();

  expect(pollNotifications).toHaveBeenCalledWith(42);
  expect(window.localStorage.getItem("hx_notify_since_id")).toBe("44");
  expect(notificationInstances).toHaveLength(2);
  expect(notificationInstances[0].title).toBe("新邮件 · a@example.com");
  expect(notificationInstances[0].options?.body).toContain("验证码: 482913");
  expect(notificationInstances[1].options?.body).toBe("Login code");
});

test("does not poll when disabled or permission missing", async () => {
  setBrowserNotifyEnabled(false);
  await pollOnce();
  expect(pollNotifications).not.toHaveBeenCalled();

  setBrowserNotifyEnabled(true);
  FakeNotification.permission = "denied";
  await pollOnce();
  expect(pollNotifications).not.toHaveBeenCalled();
});

test("a failing poll keeps the cursor unchanged for retry", async () => {
  window.localStorage.setItem("hx_notify_since_id", "42");
  pollNotifications.mockRejectedValue(new Error("network down"));

  await pollOnce();

  expect(window.localStorage.getItem("hx_notify_since_id")).toBe("42");
  expect(notificationInstances).toHaveLength(0);
});
