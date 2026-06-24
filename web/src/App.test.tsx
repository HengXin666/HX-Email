import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";
import { ToastProvider } from "./components/ui/Toast";
import { Login } from "./pages/Login";
import { AppProvider, useApp } from "./store/AppContext";

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

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

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
  expect(loginButtons[0]).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: "记住密码" })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "自动登录" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "去注册" })).toBeEnabled();
});

const LogoutHarness: React.FC = () => {
  const { token, logout } = useApp();

  if (!token) return <Login />;

  return (
    <button type="button" onClick={() => void logout()}>
      退出登录
    </button>
  );
};

test("logout suppresses saved auto-login credentials", async () => {
  window.localStorage.setItem("hx_token", "old-token");
  window.localStorage.setItem(
    "hx_user",
    JSON.stringify({ id: 1, username: "admin", is_admin: true }),
  );
  window.localStorage.setItem("hx_last_username", "admin");
  window.localStorage.setItem("hx_password", "admin");
  window.localStorage.setItem("hx_remember_password", "true");
  window.localStorage.setItem("hx_auto_login", "true");

  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path === "/auth/logout") {
      return new Response(null, { status: 204 });
    }
    if (path === "/auth/login") {
      return Response.json({
        access_token: "new-token",
        user: { id: 1, username: "admin", is_admin: true },
      });
    }
    return Response.json({});
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <MemoryRouter initialEntries={["/overview"]}>
      <AppProvider>
        <ToastProvider>
          <LogoutHarness />
        </ToastProvider>
      </AppProvider>
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByRole("button", { name: "退出登录" }));

  await screen.findByRole("button", { name: "登录" });
  await waitFor(() => {
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/auth/login",
      expect.objectContaining({ method: "POST" }),
    );
  });
  expect(window.localStorage.getItem("hx_auto_login")).toBe("false");
});
