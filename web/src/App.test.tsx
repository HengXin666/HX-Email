import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  vi.restoreAllMocks();
});

test("loads the dark HX Email workbench entry screen", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: /HX Email/i })).toBeInTheDocument();
  expect(screen.getByLabelText("用户名")).toBeInTheDocument();
  expect(screen.getByLabelText("密码")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "登录" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "注册" })).not.toBeInTheDocument();
  expect(document.documentElement).toHaveClass("dark");
});

test("submits login credentials to the authentication endpoint", async () => {
  const setItem = vi.fn();
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          access_token: "test-token",
          user: { id: 1, username: "owner", is_admin: true },
        }),
        { headers: { "Content-Type": "application/json" }, status: 200 },
      ),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          usable_emails: [
            {
              id: 1,
              address: "owner@example.com",
              label: "Owner mailbox",
              kind: "primary",
              status: "active",
              group: null,
              tags: [],
              platform_binding_count: 0,
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
        { headers: { "Content-Type": "application/json" }, status: 200 },
      ),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          usable_email_count: 1,
          active_email_count: 1,
          account_count: 1,
          temp_email_count: 0,
          platform_count: 0,
          binding_count: 0,
          pool_available_count: 0,
          pool_claimed_count: 0,
          verification_count: 0,
        }),
        { headers: { "Content-Type": "application/json" }, status: 200 },
      ),
    )
    .mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ email_accounts: [], entries: [], platforms: [] }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      })),
    );
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: { setItem },
  });

  render(<App />);
  fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "owner" } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret-pass" } });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(fetchMock).toHaveBeenCalledWith("/auth/login", {
    body: JSON.stringify({ username: "owner", password: "secret-pass" }),
    headers: { "Content-Type": "application/json" },
    method: "POST",
  });
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  expect(fetchMock).toHaveBeenNthCalledWith(2, "/workbench/usable-emails", {
    headers: { Authorization: "Bearer test-token" },
  });
  expect(fetchMock).toHaveBeenNthCalledWith(3, "/workbench/overview", {
    headers: { Authorization: "Bearer test-token" },
  });
  expect(setItem).toHaveBeenCalledWith("hx-email-token", "test-token");
  expect(screen.getByRole("status")).toHaveTextContent("登录成功");
  expect(screen.getByRole("heading", { name: "Outlook Email Plus 工作台" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "账号管理" }));
  expect(screen.getByText("owner@example.com")).toBeInTheDocument();
});

test("shows the registration form when registration is enabled", () => {
  render(<App registrationEnabled />);

  expect(screen.getByRole("heading", { name: "注册 HX Email" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "注册" })).toBeEnabled();
});

test("shows the primary usable email workbench when signed in", () => {
  render(
    <App
      session={{
        username: "alice",
        usableEmails: [
          {
            id: 1,
            address: "alice@example.com",
            label: "Alice IMAP",
            kind: "primary",
            status: "active",
          },
        ],
      }}
    />,
  );

  expect(screen.getByRole("heading", { name: "Outlook Email Plus 工作台" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "账号管理" }));
  expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  expect(screen.getAllByText("主邮箱地址").length).toBeGreaterThanOrEqual(1);
  expect(screen.getByRole("button", { name: "停用" })).toBeEnabled();
});

test("shows alias usable emails as independent rows", () => {
  render(
    <App
      session={{
        username: "alice",
        usableEmails: [
          {
            id: 1,
            address: "alice@example.com",
            label: "Alice IMAP",
            kind: "primary",
            status: "active",
          },
          {
            id: 2,
            address: "alias@example.com",
            label: "Campaign alias",
            kind: "alias",
            status: "active",
          },
        ],
      }}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "账号管理" }));
  expect(screen.getByText("alias@example.com")).toBeInTheDocument();
  expect(screen.getAllByText("别名邮箱地址").length).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByRole("button", { name: "停用" })).toHaveLength(2);
});

test("shows workbench filters, grouping, tags and pagination", () => {
  render(
    <App
      session={{
        username: "alice",
        usableEmails: [
          {
            id: 2,
            address: "alias@example.com",
            label: "Campaign alias",
            kind: "alias",
            status: "active",
            group: { id: 1, name: "注册用途", color: "#58a6ff" },
            tags: [{ id: 1, name: "验证码", color: "#238636" }],
            platformBindingCount: 0,
          },
        ],
        page: 1,
        pageSize: 50,
        total: 1,
      }}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "账号管理" }));
  expect(screen.getByRole("searchbox", { name: "关键词" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "类型" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "状态" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "平台绑定" })).toBeInTheDocument();
  expect(screen.getByText("alias@example.com")).toBeInTheDocument();
});
