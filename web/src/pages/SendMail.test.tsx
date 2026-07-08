import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { api } from "../api/client";
import { ToastProvider } from "../components/ui/Toast";
import { SendMail } from "./SendMail";

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

vi.mock("../api/client", () => ({
  api: {
    sendDebugEmail: vi.fn(),
  },
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({
    emails: [
      {
        id: 12,
        address: "sender@gmail.com",
        label: "Sender",
        kind: "primary",
        status: "active",
        email_account_id: 5,
      },
    ],
    refreshEmails: vi.fn(),
  }),
}));

afterEach(() => {
  vi.clearAllMocks();
});

test("send mail page blocks blank recipient before posting", async () => {
  render(
    <ToastProvider>
      <SendMail />
    </ToastProvider>,
  );

  await waitFor(() => {
    expect(screen.getByLabelText("发件来源")).toHaveValue("12");
  });
  fireEvent.submit(screen.getByRole("button", { name: "发送" }).closest("form")!);

  await screen.findByText("请填写收件人");
  expect(api.sendDebugEmail).not.toHaveBeenCalled();
});

test("send mail page posts trimmed recipient", async () => {
  vi.mocked(api.sendDebugEmail).mockResolvedValue({
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
  render(
    <ToastProvider>
      <SendMail />
    </ToastProvider>,
  );

  await waitFor(() => {
    expect(screen.getByLabelText("发件来源")).toHaveValue("12");
  });
  fireEvent.change(screen.getByLabelText("收件人"), {
    target: { value: "  receiver@example.com  " },
  });
  fireEvent.submit(screen.getByRole("button", { name: "发送" }).closest("form")!);

  await waitFor(() => {
    expect(api.sendDebugEmail).toHaveBeenCalledWith(
      12,
      expect.objectContaining({ recipient: "receiver@example.com" }),
    );
  });
});
