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
