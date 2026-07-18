import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { ToastProvider } from "../components/ui/Toast";
import { TokenTool } from "./TokenTool";

const getGoogleOAuthConfig = vi.fn();
const getTokenToolConfig = vi.fn();
const listTokenToolAccounts = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    getGoogleOAuthConfig: (...args: unknown[]) => getGoogleOAuthConfig(...args),
    getTokenToolConfig: (...args: unknown[]) => getTokenToolConfig(...args),
    listTokenToolAccounts: (...args: unknown[]) => listTokenToolAccounts(...args),
  },
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({ refreshAccounts: vi.fn(), refreshEmails: vi.fn() }),
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
