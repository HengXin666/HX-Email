import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ToastProvider } from "../components/ui/Toast";
import type { EmailAccount, UsableEmail } from "../types";
import { Accounts } from "./Accounts";

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({
      children,
      animate: _animate,
      exit: _exit,
      initial: _initial,
      layout: _layout,
      transition: _transition,
      whileHover: _whileHover,
      whileTap: _whileTap,
      ...props
    }: React.HTMLAttributes<HTMLDivElement> & Record<string, unknown>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

const listPoolEntries = vi.fn();
const getMessagesPage = vi.fn();
const readVerification = vi.fn();
const verificationHistory = vi.fn();
const listBindings = vi.fn();
const fetchEmails = vi.fn();

const primaryEmail: UsableEmail = {
  id: 7,
  address: "owner@example.com",
  label: "Owner",
  kind: "primary",
  status: "active",
  email_account_id: 3,
  platform_binding_count: 0,
};

const account: EmailAccount = {
  id: 3,
  provider: "gmail",
  primary_address: "owner@example.com",
  display_name: "Gmail Owner",
  status: "active",
  usable_emails: [primaryEmail],
  last_refresh_at: "2026-07-04T10:00:00Z",
};

vi.mock("../api/client", () => ({
  api: {
    fetchEmails: (...args: unknown[]) => fetchEmails(...args),
    getMessagesPage: (...args: unknown[]) => getMessagesPage(...args),
    listBindings: (...args: unknown[]) => listBindings(...args),
    listPoolEntries: (...args: unknown[]) => listPoolEntries(...args),
    readVerification: (...args: unknown[]) => readVerification(...args),
    verificationHistory: (...args: unknown[]) => verificationHistory(...args),
  },
  streamRefresh: vi.fn(),
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({
    accounts: [account],
    emails: [primaryEmail],
    groups: [],
    platforms: [],
    tags: [],
    addAlias: vi.fn(),
    createGroup: vi.fn(),
    deleteGroup: vi.fn(),
    organizeEmail: vi.fn(),
    refreshAccounts: vi.fn(),
    refreshEmails: vi.fn(),
    updateGroup: vi.fn(),
  }),
}));

function renderAccounts(): void {
  render(
    <ToastProvider>
      <Accounts />
    </ToastProvider>,
  );
}

beforeEach(() => {
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: vi.fn(() => true),
  });
  listPoolEntries.mockResolvedValue([]);
  getMessagesPage.mockResolvedValue({
    messages: [
      {
        id: 101,
        from_address: "service@example.com",
        recipient_address: "owner@example.com",
        subject: "Login code",
        body: "Your code is 123456",
        received_at: "2026-07-04T10:01:00Z",
        created_at: "2026-07-04T10:01:00Z",
      },
    ],
    total: 1,
  });
  readVerification.mockResolvedValue({ matches: [{ code: "123456", link: null }] });
  verificationHistory.mockResolvedValue({ matches: [{ code: "123456", link: null }] });
  listBindings.mockResolvedValue([]);
  fetchEmails.mockResolvedValue({
    account_id: 3,
    email: "owner@example.com",
    messages_stored: 0,
    codes_found: 0,
    error: "",
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

test("email detail uses cached verification history instead of live verification reads", async () => {
  renderAccounts();

  const emailCard = screen.getByText("Owner").closest(".cursor-pointer");
  expect(emailCard).not.toBeNull();
  fireEvent.click(emailCard as HTMLElement);

  await waitFor(() => {
    expect(getMessagesPage).toHaveBeenCalledWith(7, expect.any(Number), 0);
  });
  expect(verificationHistory).toHaveBeenCalledWith(7);
  expect(readVerification).not.toHaveBeenCalled();
  expect(screen.getByText("Login code")).toBeInTheDocument();
});

test("verification button uses incremental fetch before reading cached history", async () => {
  renderAccounts();

  fireEvent.click(screen.getByTitle("获取验证码"));

  await waitFor(() => {
    expect(fetchEmails).toHaveBeenCalledWith(7);
  });
  expect(verificationHistory).toHaveBeenCalledWith(7);
  expect(readVerification).not.toHaveBeenCalled();
});
