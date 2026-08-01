import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

import { ToastProvider } from "../components/ui/Toast";
import { TempMail } from "./TempMail";

const tempMessages = vi.fn();
const tempCodes = vi.fn();
const tempLinks = vi.fn();

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({
      children,
      whileHover: _whileHover,
      whileTap: _whileTap,
      ...props
    }: React.HTMLAttributes<HTMLDivElement> & {
      whileHover?: unknown;
      whileTap?: unknown;
    }) => <div {...props}>{children}</div>,
  },
}));

vi.mock("../api/client", () => ({
  api: {
    archiveTempMail: vi.fn(),
    tempMessages: (...args: unknown[]) => tempMessages(...args),
    tempCodes: (...args: unknown[]) => tempCodes(...args),
    tempLinks: (...args: unknown[]) => tempLinks(...args),
  },
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({
    emails: [
      {
        id: 7,
        address: "signup@example.test",
        label: "Microsoft test",
        kind: "temp",
        status: "active",
      },
    ],
    createTempMail: vi.fn(),
    refreshEmails: vi.fn(),
  }),
}));

test("renders a Microsoft security code returned by the temp-mail API", async () => {
  tempMessages.mockResolvedValue([
    {
      id: "microsoft-message",
      from_address: "account-security-noreply@accountprotection.microsoft.com",
      subject: "Microsoft 帐户安全代码",
      text: "",
      html: [
        "<div><strong>安全代码:</strong> <span>432939</span></div>",
        "<p>仅在官方网站输入此代码</p>",
        '<script>window.alert("unsafe")</script>',
      ].join(""),
    },
  ]);
  tempCodes.mockResolvedValue([{ message_id: "microsoft-message", code: "432939" }]);
  tempLinks.mockResolvedValue([]);

  render(
    <MemoryRouter>
      <ToastProvider>
        <TempMail />
      </ToastProvider>
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByText("Microsoft test"));

  expect(await screen.findAllByText("432939")).toHaveLength(2);
  expect(tempCodes).toHaveBeenCalledWith(7);
  expect(screen.getByText("最新验证码")).toBeInTheDocument();
  expect(screen.getByText("仅在官方网站输入此代码")).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
});
