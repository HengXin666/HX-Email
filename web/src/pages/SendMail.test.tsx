import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { api } from "../api/client";
import { SendMail } from "./SendMail";

const refreshEmailsMock = vi.fn(async () => {});
const toastMock = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    sendDebugEmail: vi.fn(),
  },
}));

vi.mock("../components/ui/Toast", () => ({
  useToast: () => ({
    toast: toastMock,
  }),
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({
    emails: [
      {
        id: 12,
        address: "sender@example.com",
        label: "",
        kind: "primary",
        status: "active",
        email_account_id: 5,
      },
    ],
    refreshEmails: refreshEmailsMock,
  }),
}));

beforeEach(() => {
  refreshEmailsMock.mockClear();
  toastMock.mockClear();
  vi.mocked(api.sendDebugEmail).mockReset();
});

test("blocks sending when recipient is blank", async () => {
  render(<SendMail />);

  fireEvent.click(screen.getByRole("button", { name: "发送" }));

  expect(await screen.findByText("请填写收件人邮箱后再发送")).toBeInTheDocument();
  expect(toastMock).toHaveBeenCalledWith("请填写收件人邮箱后再发送", "error");
  expect(api.sendDebugEmail).not.toHaveBeenCalled();
});

test("keeps recipient state and sends trimmed recipient", async () => {
  vi.mocked(api.sendDebugEmail).mockResolvedValue({
    success: true,
    code: "sent",
    message: "Debug email sent to receiver@example.com.",
    credential_policy: "Uses account SMTP credentials.",
    credential_strategy: "email_account_smtp_password",
    from_address: "sender@example.com",
    to_address: "receiver@example.com",
    usable_email_id: 12,
    email_account_id: 5,
    smtp_host: "smtp.example.com",
    smtp_port: 587,
    security: "starttls",
    actions: [],
  });
  render(<SendMail />);

  const recipientInput = screen.getByLabelText("收件人");
  fireEvent.change(recipientInput, { target: { value: "  receiver@example.com  " } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));

  await waitFor(() => {
    expect(api.sendDebugEmail).toHaveBeenCalledWith(12, {
      recipient: "receiver@example.com",
      subject: "HX-Email debug email",
      body: "This is a debug email sent by HX-Email.",
    });
  });
  expect(recipientInput).toHaveValue("  receiver@example.com  ");
});
