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
const getEmailAccount = vi.fn();
const readVerification = vi.fn();
const verificationHistory = vi.fn();
const listBindings = vi.fn();
const fetchEmails = vi.fn();
const updateEmailAccount = vi.fn();

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

let mockEmails: UsableEmail[] = [primaryEmail];
let mockAccounts: EmailAccount[] = [account];

vi.mock("../api/client", () => ({
  api: {
    fetchEmails: (...args: unknown[]) => fetchEmails(...args),
    getEmailAccount: (...args: unknown[]) => getEmailAccount(...args),
    getMessagesPage: (...args: unknown[]) => getMessagesPage(...args),
    listBindings: (...args: unknown[]) => listBindings(...args),
    listPoolEntries: (...args: unknown[]) => listPoolEntries(...args),
    readVerification: (...args: unknown[]) => readVerification(...args),
    updateEmailAccount: (...args: unknown[]) => updateEmailAccount(...args),
    verificationHistory: (...args: unknown[]) => verificationHistory(...args),
  },
  streamRefresh: vi.fn(),
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({
    accounts: mockAccounts,
    emails: mockEmails,
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
  mockEmails = [primaryEmail];
  mockAccounts = [account];
  Object.defineProperty(document, "execCommand", {
    configurable: true,
    value: vi.fn(() => true),
  });
  listPoolEntries.mockResolvedValue([]);
  getEmailAccount.mockResolvedValue(account);
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

test("settings credential tab uses account detail provider when list cache misses the account", async () => {
  const outlookEmail: UsableEmail = {
    id: 11,
    address: "late-owner@outlook.com",
    label: "Late Outlook",
    kind: "primary",
    status: "active",
    email_account_id: 99,
    platform_binding_count: 0,
  };
  const outlookAccount: EmailAccount & {
    imap_password: string;
    refresh_token: string;
  } = {
    id: 99,
    provider: "outlook",
    primary_address: "late-owner@outlook.com",
    display_name: "Late Outlook",
    status: "active",
    usable_emails: [outlookEmail],
    imap_password: "outlook-password",
    client_id: "client-id-from-detail",
    refresh_token: "refresh-token-from-detail",
  };
  mockEmails = [outlookEmail];
  mockAccounts = [];
  getEmailAccount.mockResolvedValue(outlookAccount);

  renderAccounts();

  fireEvent.click(screen.getByTitle("设置"));
  fireEvent.click(screen.getByRole("button", { name: "凭证" }));

  await waitFor(() => {
    expect(getEmailAccount).toHaveBeenCalledWith(99);
  });
  expect(await screen.findByDisplayValue("outlook-password")).toBeInTheDocument();
  expect(screen.getByDisplayValue("client-id-from-detail")).toBeInTheDocument();
  expect(screen.getByDisplayValue("refresh-token-from-detail")).toBeInTheDocument();
});
