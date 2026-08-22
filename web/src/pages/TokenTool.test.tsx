import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { ToastProvider } from "../components/ui/Toast";
import { TokenTool } from "./TokenTool";

const getGoogleOAuthConfig = vi.fn();
const getTokenToolConfig = vi.fn();
const listTokenToolAccounts = vi.fn();
const prepareGoogleOAuthNew = vi.fn();
const getGoogleOAuthFlowStatus = vi.fn();
const createEmailAccount = vi.fn();
const listEmailAccounts = vi.fn();
const streamRefresh = vi.fn();
const refreshAccounts = vi.fn();
const refreshEmails = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    getGoogleOAuthConfig: (...args: unknown[]) => getGoogleOAuthConfig(...args),
    getTokenToolConfig: (...args: unknown[]) => getTokenToolConfig(...args),
    listTokenToolAccounts: (...args: unknown[]) => listTokenToolAccounts(...args),
    prepareGoogleOAuthNew: (...args: unknown[]) => prepareGoogleOAuthNew(...args),
    getGoogleOAuthFlowStatus: (...args: unknown[]) => getGoogleOAuthFlowStatus(...args),
    createEmailAccount: (...args: unknown[]) => createEmailAccount(...args),
    listEmailAccounts: (...args: unknown[]) => listEmailAccounts(...args),
  },
  streamRefresh: (...args: unknown[]) => streamRefresh(...args),
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({ refreshAccounts, refreshEmails }),
}));

beforeEach(() => {
  window.localStorage.setItem("hx_token_tool_provider", "google");
  listEmailAccounts.mockResolvedValue([]);
  getTokenToolConfig.mockResolvedValue({
    client_id: "microsoft-client",
    redirect_uri: "http://localhost/token-tool/callback",
    scope: "offline_access",
    tenant: "consumers",
    prompt_consent: true,
  });
  listTokenToolAccounts.mockResolvedValue([
    { id: 7, email: "owner@gmail.com", status: "active", provider: "gmail" },
  ]);
  getGoogleOAuthConfig.mockResolvedValue({
    client_id: "google-client",
    redirect_uri: "http://localhost/api/v1/google-oauth/callback",
    has_client_secret: true,
  });
  prepareGoogleOAuthNew.mockResolvedValue({
    authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?state=token-new",
    state: "token-new",
  });
  getGoogleOAuthFlowStatus.mockResolvedValue({
    status: "pending",
    email: "",
    error: "",
  });
  createEmailAccount.mockResolvedValue({
    id: 8,
    provider: "gmail",
    primary_address: "new-owner@gmail.com",
    display_name: "new-owner@gmail.com",
    status: "active",
    usable_emails: [],
  });
});

test("token tool restores Google provider and shows the aligned guide", async () => {
  render(
    <MemoryRouter>
      <ToastProvider>
        <TokenTool />
      </ToastProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByText("Google 一键授权流程")).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "OAuth 服务商" })).toHaveTextContent("Google Gmail");
  expect(screen.getByText("自动持久化")).toBeInTheDocument();

  fireEvent.click(screen.getByText("页面 Token").closest("button") as HTMLButtonElement);
  expect(await screen.findByText("Google OAuth 一键授权")).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Gmail 账号" })).toHaveTextContent("owner@gmail.com");
  expect(getGoogleOAuthConfig).toHaveBeenCalled();
});

test("creating a Gmail account authorizes without typing an email and refreshes workspaces", async () => {
  window.localStorage.setItem("hx_token_tool_active_tab", "page-token");
  listTokenToolAccounts.mockResolvedValue([]);

  render(
    <MemoryRouter>
      <ToastProvider>
        <TokenTool />
      </ToastProvider>
    </MemoryRouter>,
  );

  const generateButton = await screen.findByRole("button", { name: "生成授权链接" });
  await waitFor(() => expect(generateButton).toBeEnabled());
  fireEvent.click(generateButton);

  await waitFor(() => {
    expect(prepareGoogleOAuthNew).toHaveBeenCalledWith(null);
  });
  expect(screen.queryByRole("textbox", { name: "Gmail 地址" })).not.toBeInTheDocument();

  getGoogleOAuthFlowStatus.mockResolvedValueOnce({
    status: "done",
    email: "new-owner@gmail.com",
    error: "",
  });
  fireEvent.click(screen.getByRole("button", { name: "我已完成授权" }));

  await waitFor(() => {
    expect(refreshAccounts).toHaveBeenCalledOnce();
  });
  expect(refreshEmails).toHaveBeenCalledOnce();
});

test("stats sidebar shows credential overview and age-based picking", async () => {
  listEmailAccounts.mockResolvedValue([
    {
      id: 1,
      provider: "outlook",
      primary_address: "old@outlook.com",
      display_name: "Old",
      status: "active",
      has_refresh_token: true,
      last_refresh_at: "2026-08-20T10:00:00Z",
      created_at: "2026-05-01T00:00:00Z",
      usable_emails: [],
    },
    {
      id: 2,
      provider: "gmail",
      primary_address: "new@gmail.com",
      display_name: "New",
      status: "active",
      has_refresh_token: true,
      refresh_failed_at: "2026-08-21T10:00:00Z",
      created_at: "2026-08-10T00:00:00Z",
      usable_emails: [],
    },
  ]);

  render(
    <MemoryRouter>
      <ToastProvider>
        <TokenTool />
      </ToastProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByText("账号统计")).toBeInTheDocument();
  expect(screen.getByText("凭证概览")).toBeInTheDocument();
  expect(screen.getByText("凭证有效")).toBeInTheDocument();
  expect(screen.getByText("凭证失效")).toBeInTheDocument();
  expect(screen.getByText("存活时间分布")).toBeInTheDocument();
  expect(screen.getByText("按天数取号")).toBeInTheDocument();
  expect(screen.getByText("刷新与巡检")).toBeInTheDocument();

  // 点击存活区间触发按天数取号 (走 /email-accounts?min_age_days&max_age_days)
  fireEvent.click(screen.getByTitle("筛选存活 14-30天 的账号"));
  await waitFor(() => {
    expect(listEmailAccounts).toHaveBeenLastCalledWith({ min_age_days: 14, max_age_days: 30 });
  });
  expect(await screen.findByText("2 个")).toBeInTheDocument();
  expect(screen.getByText("复制邮箱")).toBeInTheDocument();
});
