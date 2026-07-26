import { useEffect } from "react";
import { api } from "../api/client";
import type { MailNotification } from "../types";

const ENABLED_KEY = "hx_browser_notify_enabled";
const CURSOR_KEY = "hx_notify_since_id";
const NOTIFY_POLL_INTERVAL_MS = 30_000;

export function isBrowserNotifyEnabled(): boolean {
  try {
    return window.localStorage.getItem(ENABLED_KEY) === "1";
  } catch {
    return false;
  }
}

export function setBrowserNotifyEnabled(enabled: boolean): void {
  try {
    window.localStorage.setItem(ENABLED_KEY, enabled ? "1" : "0");
  } catch {
    // localStorage unavailable (private mode) — notifications stay off
  }
}

function canNotify(): boolean {
  return typeof Notification !== "undefined" && Notification.permission === "granted";
}

function showMailNotification(item: MailNotification): void {
  const body = item.verification_code
    ? `${item.subject || "(无主题)"}\n验证码: ${item.verification_code}`
    : item.subject || "(无主题)";
  const notification = new Notification(`新邮件 · ${item.address}`, {
    body,
    tag: `hx-mail-${item.id}`,
  });
  notification.onclick = () => {
    window.focus();
    notification.close();
  };
}

/** One poll round: fetch mail newer than the stored cursor and notify. Exported for tests. */
export async function pollOnce(): Promise<void> {
  if (!isBrowserNotifyEnabled() || !canNotify()) return;
  let sinceId = -1;
  try {
    const stored = window.localStorage.getItem(CURSOR_KEY);
    const parsed = stored === null ? -1 : Number(stored);
    sinceId = Number.isFinite(parsed) ? parsed : -1;
  } catch {
    return;
  }
  try {
    const result = await api.pollNotifications(sinceId);
    window.localStorage.setItem(CURSOR_KEY, String(result.latest_id));
    result.notifications.forEach(showMailNotification);
  } catch {
    // Transient network/auth error — retry on the next tick
  }
}

/**
 * Poll the new-mail feed while logged in and surface browser notifications.
 * The first poll only initializes the server-side cursor (no flood of old mail);
 * per-email / per-group muting is applied server-side.
 */
export function useBrowserNotifications(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    void pollOnce();
    const timer = window.setInterval(() => void pollOnce(), NOTIFY_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [active]);
}
