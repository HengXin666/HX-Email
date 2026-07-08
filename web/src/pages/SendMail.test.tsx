import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, expect, test, vi } from "vitest";

import { ToastProvider } from "../components/ui/Toast";
import { SendMail } from "./SendMail";

const sendDebugEmailMock = vi.hoisted(() => vi.fn());
const refreshEmailsMock = vi.hoisted(() => vi.fn());

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
    sendDebugEmail: sendDebugEmailMock,
  },
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({
    emails: [
      {
        id: 12,
        address: "sender@gmail.com",
        label: "",
        kind: "primary",
        status: "active",
        email_account_id: 5,
        provider: "gmail",
      },
    ],
    refreshEmails: refreshEmailsMock,
  }),
}));

afterEach(() => {
  vi.clearAllMocks();
});

function renderSendMail(): void {
  render(
    <ToastProvider>
      <SendMail />
    </ToastProvider>,
  );
}

test("requires recipient before sending debug email", () => {
  renderSendMail();

  const sendButton = screen.getByRole("button", { name: "发送" });

  expect(sendButton).toBeDisabled();
  expect(sendDebugEmailMock).not.toHaveBeenCalled();
});

test("sends trimmed required fields to the backend", async () => {
  sendDebugEmailMock.mockResolvedValue({
    success: true,
    code: "sent",
    message: "Debug email sent to receiver@example.com.",
    credential_policy: "Uses account SMTP credentials.",
    credential_strategy: "email_account_smtp_password",
    from_address: "sender@gmail.com",
    to_address: "receiver@example.com",
    usable_email_id: 12,
    email_account_id: 5,
    smtp_host: "smtp.gmail.com",
    smtp_port: 587,
    security: "starttls",
    actions: [],
  });
  renderSendMail();

  fireEvent.change(screen.getByLabelText("收件人"), {
    target: { value: " receiver@example.com " },
  });
  fireEvent.change(screen.getByLabelText("主题"), { target: { value: " Debug " } });
  fireEvent.change(screen.getByLabelText("正文"), { target: { value: " Hello " } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));

  await waitFor(() => {
    expect(sendDebugEmailMock).toHaveBeenCalledWith(12, {
      recipient: "receiver@example.com",
      subject: "Debug",
      body: "Hello",
    });
  });
});
