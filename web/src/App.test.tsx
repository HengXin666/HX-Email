import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

import App from "./App";
import { ToastProvider } from "./components/ui/Toast";
import { AppProvider } from "./store/AppContext";

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
      <div {...props}>{children}</div>
    ),
    main: ({ children, ...props }: React.HTMLAttributes<HTMLElement>) => (
      <main {...props}>{children}</main>
    ),
  },
}));

test("renders the all-web login experience", () => {
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <AppProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AppProvider>
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { name: "HX-Email" })).toBeInTheDocument();
  expect(screen.getByLabelText("用户名")).toHaveValue("");
  expect(screen.getByLabelText("密码")).toHaveValue("");
  const loginButtons = screen.getAllByRole("button", { name: "登录" });
  expect(loginButtons).toHaveLength(1);
  expect(loginButtons[0]).toBeEnabled();
  expect(screen.getByRole("checkbox", { name: "记住密码" })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "自动登录" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "去注册" })).toBeEnabled();
});
