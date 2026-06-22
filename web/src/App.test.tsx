import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "./App";

test("loads the dark HX Email workbench entry screen", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: /HX Email/i })).toBeInTheDocument();
  expect(screen.getByLabelText("用户名")).toBeInTheDocument();
  expect(screen.getByLabelText("密码")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "登录" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "注册" })).not.toBeInTheDocument();
  expect(document.documentElement).toHaveClass("dark");
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

  expect(screen.getByRole("heading", { name: "可用邮箱工作台" })).toBeInTheDocument();
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

  expect(screen.getByRole("searchbox", { name: "关键词" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "类型" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "状态" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "平台绑定" })).toBeInTheDocument();
  expect(screen.getByText("注册用途")).toBeInTheDocument();
  expect(screen.getByText("验证码")).toBeInTheDocument();
  expect(screen.getAllByText("未绑定平台").length).toBeGreaterThanOrEqual(1);
  expect(screen.getByText("第 1 页 / 共 1 条")).toBeInTheDocument();
});
