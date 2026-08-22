import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { ToastProvider } from "../components/ui/Toast";
import { TokenTool } from "./TokenTool";

const getGoogleOAuthConfig = vi.fn();
const getTokenToolConfig = vi.fn();
const listTokenToolAccounts = vi.fn();
const prepareGoogleOAuthNew = vi.fn();
const getGoogleOAuthFlowStatus = vi.fn();
const createEmailAccount = vi.fn();
const getAccountStats = vi.fn();
const listEmailAccounts = vi.fn();
const patrolStatus = vi.fn();
const patrolStart = vi.fn();
const patrolPause = vi.fn();
const patrolResume = vi.fn();
const patrolStop = vi.fn();
const subscribePatrol = vi.fn();
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
    getAccountStats: (...args: unknown[]) => getAccountStats(...args),
    listEmailAccounts: (...args: unknown[]) => listEmailAccounts(...args),
    patrolStatus: (...args: unknown[]) => patrolStatus(...args),
    patrolStart: (...args: unknown[]) => patrolStart(...args),
    patrolPause: (...args: unknown[]) => patrolPause(...args),
    patrolResume: (...args: unknown[]) => patrolResume(...args),
    patrolStop: (...args: unknown[]) => patrolStop(...args),
  },
  subscribePatrol: (...args: unknown[]) => subscribePatrol(...args),
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({ refreshAccounts, refreshEmails }),
}));

beforeEach(() => {
  window.localStorage.setItem("hx_token_tool_provider", "google");
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
  getAccountStats.mockResolvedValue({
    total: 2,
    oauth: 2,
    microsoft: 1,
    google: 1,
    valid: 1,
    invalid: 1,
    unknown: 0,
    failed_refresh: 1,
    last_refresh: null,
    by_provider: [
      { provider: "outlook", count: 1 },
      { provider: "gmail", count: 1 },
    ],
    by_group: [],
    ungrouped: { total: 2, valid: 1, invalid: 1 },
    error_categories: [
      { provider: "outlook", category: "token_expired", label: "令牌失效/过期", count: 1 },
    ],
    age_buckets: [
      { label: "<7天", min: 0, max: 7, valid: 0, invalid: 0, unknown: 0 },
      { label: "7-14天", min: 7, max: 14, valid: 0, invalid: 0, unknown: 0 },
      { label: "14-30天", min: 14, max: 30, valid: 0, invalid: 0, unknown: 0 },
      { label: "30-60天", min: 30, max: 60, valid: 1, invalid: 0, unknown: 0 },
      { label: "60-90天", min: 60, max: 90, valid: 0, invalid: 0, unknown: 0 },
      { label: "90-180天", min: 90, max: 180, valid: 0, invalid: 0, unknown: 0 },
      { label: "180天+", min: 180, max: null, valid: 0, invalid: 1, unknown: 0 },
    ],
    daily_new: Array.from({ length: 30 }, (_, i) => ({
      date: `2026-07-${String(i + 1).padStart(2, "0")}`,
      count: i % 3,
    })),
    daily_refresh: Array.from({ length: 30 }, (_, i) => ({
      date: `2026-07-${String(i + 1).padStart(2, "0")}`,
      success: 2,
      failed: i % 2,
    })),
  });
  listEmailAccounts.mockResolvedValue([]);
  patrolStatus.mockResolvedValue({
    status: "idle",
    mode: "",
    mode_label: "",
    group_id: null,
    total: 0,
    current: 0,
    success: 0,
    failed: 0,
    email: "",
    started_at: null,
    finished_at: null,
    error: "",
  });
  subscribePatrol.mockResolvedValue(undefined);
});

test("token tool restores Google provider and shows the aligned guide", async () => {
  render(
    <ToastProvider>
      <TokenTool />
    </ToastProvider>,
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
    <ToastProvider>
      <TokenTool />
    </ToastProvider>,
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

test("account-stats tab follows the selected provider from the dropdown", async () => {
  window.localStorage.setItem("hx_token_tool_provider", "microsoft");
  window.localStorage.setItem("hx_token_tool_active_tab", "guide");
  render(
    <ToastProvider>
      <TokenTool />
    </ToastProvider>,
  );

  fireEvent.click(screen.getByText("账号统计"));
  expect(await screen.findByText("凭证概览")).toBeInTheDocument();
  // 统计请求带上当前服务商 (microsoft)
  await waitFor(() => expect(getAccountStats).toHaveBeenCalledWith("microsoft"));
  // 卡片标题标注当前服务商
  expect(screen.getAllByText(/Microsoft \(Outlook\)/).length).toBeGreaterThan(0);
  expect(screen.getByText("刷新失败原因分布（近 30 天，按错误码分类）")).toBeInTheDocument();
  expect(screen.getByText("令牌失效/过期")).toBeInTheDocument();
});
