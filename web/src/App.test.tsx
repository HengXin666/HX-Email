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
  expect(screen.getByText("主邮箱地址")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "停用" })).toBeEnabled();
});
