import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ToastProvider } from "../components/ui/Toast";
import type { EmailAccount, SSERefreshEvent, UsableEmail } from "../types";
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
  Reorder: {
    Group: ({
      children,
      values: _values,
      onReorder: _onReorder,
      ...props
    }: React.HTMLAttributes<HTMLDivElement> & Record<string, unknown>) => (
      <div {...props}>{children}</div>
    ),
    Item: ({
      children,
      value: _value,
      dragListener: _dragListener,
      dragControls: _dragControls,
      ...props
    }: React.HTMLAttributes<HTMLLIElement> & Record<string, unknown>) => (
      <li {...props}>{children}</li>
    ),
  },
  useDragControls: () => ({ start: vi.fn() }),
}));

const listPoolEntries = vi.fn();
const getMessagesPage = vi.fn();
const getEmailAccount = vi.fn();
const readVerification = vi.fn();
const verificationHistory = vi.fn();
const listBindings = vi.fn();
const analyzeEmailPlatforms = vi.fn();
const fetchEmails = vi.fn();
const updateEmailAccount = vi.fn();
const getGoogleOAuthConfig = vi.fn();
const prepareGoogleOAuth = vi.fn();
const prepareGoogleOAuthNew = vi.fn();
const saveGoogleOAuthConfig = vi.fn();
const getGoogleOAuthFlowStatus = vi.fn();
const createEmailAccount = vi.fn();
const listEmailAccounts = vi.fn();
const streamRefresh = vi.fn();
const refreshAccounts = vi.fn();
const refreshEmails = vi.fn();

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
    analyzeEmailPlatforms: (...args: unknown[]) => analyzeEmailPlatforms(...args),
    listPoolEntries: (...args: unknown[]) => listPoolEntries(...args),
    readVerification: (...args: unknown[]) => readVerification(...args),
    updateEmailAccount: (...args: unknown[]) => updateEmailAccount(...args),
    getGoogleOAuthConfig: (...args: unknown[]) => getGoogleOAuthConfig(...args),
    prepareGoogleOAuth: (...args: unknown[]) => prepareGoogleOAuth(...args),
    prepareGoogleOAuthNew: (...args: unknown[]) => prepareGoogleOAuthNew(...args),
    saveGoogleOAuthConfig: (...args: unknown[]) => saveGoogleOAuthConfig(...args),
    getGoogleOAuthFlowStatus: (...args: unknown[]) => getGoogleOAuthFlowStatus(...args),
    createEmailAccount: (...args: unknown[]) => createEmailAccount(...args),
    listEmailAccounts: (...args: unknown[]) => listEmailAccounts(...args),
    verificationHistory: (...args: unknown[]) => verificationHistory(...args),
  },
  streamRefresh: (...args: unknown[]) => streamRefresh(...args),
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
    deleteGroups: vi.fn(),
    organizeEmail: vi.fn(),
    reorderGroups: vi.fn(),
    refreshAccounts,
    refreshEmails,
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
        verification_code: "123456",
        received_at: "2026-07-04T10:01:00Z",
        created_at: "2026-07-04T10:01:00Z",
      },
    ],
    total: 1,
  });
  readVerification.mockResolvedValue({ matches: [{ code: "123456", link: null }] });
  verificationHistory.mockResolvedValue({ matches: [{ code: "123456", link: null }] });
  listBindings.mockResolvedValue([]);
  analyzeEmailPlatforms.mockResolvedValue([
    {
      platform: "GitHub",
      platform_id: 5,
      message_count: 3,
      bindings_created: 1,
      bindings_skipped: 0,
    },
  ]);
  fetchEmails.mockResolvedValue({
    account_id: 3,
    email: "owner@example.com",
    messages_stored: 0,
    codes_found: 0,
    error: "",
  });
  getGoogleOAuthConfig.mockResolvedValue({
    client_id: "google-client-id",
    redirect_uri: "http://localhost:8000/api/v1/google-oauth/callback",
    has_client_secret: true,
  });
  prepareGoogleOAuth.mockResolvedValue({
    authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?state=test",
    state: "test",
  });
  prepareGoogleOAuthNew.mockResolvedValue({
    authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?state=new-account",
    state: "new-account",
  });
  getGoogleOAuthFlowStatus.mockResolvedValue({
    status: "pending",
    email: "",
    error: "",
  });
  saveGoogleOAuthConfig.mockResolvedValue({
    client_id: "google-client-id",
    redirect_uri: "http://localhost:8000/api/v1/google-oauth/callback",
    has_client_secret: true,
  });
  createEmailAccount.mockResolvedValue(account);
  listEmailAccounts.mockResolvedValue([account]);
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

test("message verification code copies without expanding the message", async () => {
  renderAccounts();

  const emailCard = screen.getByText("Owner").closest(".cursor-pointer");
  fireEvent.click(emailCard as HTMLElement);

  const codeButton = await screen.findByRole("button", { name: "复制验证码 123456" });
  fireEvent.click(codeButton);

  await waitFor(() => {
    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });
  expect(codeButton.closest(".cursor-pointer")?.querySelector(".rotate-180")).toBeNull();
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
  expect(screen.getByText("Refresh Token 已安全保存，页面不会回显")).toBeInTheDocument();
  expect(screen.queryByDisplayValue("refresh-token-from-detail")).not.toBeInTheDocument();
});

test("gmail credential tab generates a copyable authorization link instead of opening a popup", async () => {
  const openPopup = vi.spyOn(window, "open");
  renderAccounts();

  fireEvent.click(screen.getByTitle("设置"));
  fireEvent.click(screen.getByRole("button", { name: "凭证" }));
  const generateButton = await screen.findByRole("button", { name: "生成授权链接" });
  await waitFor(() => expect(generateButton).toBeEnabled());
  fireEvent.click(generateButton);

  await waitFor(() => {
    expect(prepareGoogleOAuth).toHaveBeenCalledWith(3);
  });
  expect(openPopup).not.toHaveBeenCalled();
  expect(
    screen.getByText("https://accounts.google.com/o/oauth2/v2/auth?state=test"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "复制链接" }));
  await waitFor(() => {
    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });
  openPopup.mockRestore();
});

test("gmail OAuth setup explains Cloud requirements and testing expiry", async () => {
  renderAccounts();

  fireEvent.click(screen.getByTitle("设置"));
  fireEvent.click(screen.getByRole("button", { name: "凭证" }));

  expect(await screen.findByText("1. 创建 Google Cloud 项目")).toBeInTheDocument();
  expect(screen.getByText("https://mail.google.com/")).toBeInTheDocument();
  expect(screen.getByText(/Testing 模式.*7 天/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "复制回调地址" })).toBeInTheDocument();
});

test("settings can update the primary email address", async () => {
  updateEmailAccount.mockResolvedValue(account);
  renderAccounts();

  fireEvent.click(screen.getByTitle("设置"));
  const addressInput = screen.getByRole("textbox", { name: "邮箱地址" });
  fireEvent.change(addressInput, { target: { value: "corrected@gmail.com" } });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));

  await waitFor(() => {
    expect(updateEmailAccount).toHaveBeenCalledWith(
      3,
      expect.objectContaining({ email: "corrected@gmail.com" }),
    );
  });
});

test("adding Gmail generates an authorization link without typing an email", async () => {
  renderAccounts();

  fireEvent.click(screen.getByTitle("添加邮箱"));
  fireEvent.click(screen.getByRole("combobox", { name: "服务商" }));
  fireEvent.keyDown(await screen.findByRole("option", { name: "Google Gmail" }), { key: "Enter" });

  expect(screen.getByText("Google 一键授权")).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Gmail 地址" })).not.toBeInTheDocument();
  expect(screen.queryByText("凭证信息（每行一个账户）")).not.toBeInTheDocument();

  const generateButton = await screen.findByRole("button", { name: "生成授权链接" });
  await waitFor(() => expect(generateButton).toBeEnabled());
  fireEvent.click(generateButton);
  await waitFor(() => {
    expect(prepareGoogleOAuthNew).toHaveBeenCalledWith(null);
  });
  expect(screen.getByText(/授权链接（请复制/)).toBeInTheDocument();

  getGoogleOAuthFlowStatus.mockResolvedValueOnce({
    status: "done",
    email: "owner@gmail.com",
    error: "",
  });
  fireEvent.click(screen.getByRole("button", { name: "我已完成授权" }));
  await waitFor(() => {
    expect(refreshEmails).toHaveBeenCalled();
  });
  expect(screen.getAllByText(/owner@gmail.com 授权成功/).length).toBeGreaterThan(0);
});

test("refresh all closes progress and reports the completed SSE summary", async () => {
  streamRefresh.mockImplementation(
    async (
      _url: string,
      _body: object | undefined,
      onProgress: ((event: SSERefreshEvent) => void) | undefined,
    ): Promise<void> => {
      onProgress?.({ type: "start", total: 7 });
      onProgress?.({
        type: "progress",
        current: 3,
        total: 7,
        email: "three@example.com",
        success: true,
      });
      onProgress?.({ type: "complete", total: 7, success: 6, failed: 1 });
    },
  );
  renderAccounts();

  fireEvent.click(screen.getByRole("button", { name: "刷新全部" }));
  fireEvent.click(await screen.findByRole("button", { name: "确认刷新 (1)" }));

  expect(await screen.findByText("刷新完成: 成功 6, 失败 1")).toBeInTheDocument();
  expect(screen.queryByText("正在刷新 Token...")).not.toBeInTheDocument();
  expect(refreshAccounts).toHaveBeenCalledOnce();
  expect(refreshEmails).toHaveBeenCalledOnce();
});

test("bindings tab analyze button auto-binds rule-matched platforms", async () => {
  renderAccounts();

  const emailCard = screen.getByText("Owner").closest(".cursor-pointer");
  fireEvent.click(emailCard as HTMLElement);

  fireEvent.click(await screen.findByRole("button", { name: /平台绑定/ }));
  fireEvent.click(await screen.findByRole("button", { name: /分析邮件并绑定/ }));

  await waitFor(() => {
    expect(analyzeEmailPlatforms).toHaveBeenCalledWith(7);
  });
  expect(await screen.findByText(/已自动识别并绑定/)).toBeInTheDocument();
});
