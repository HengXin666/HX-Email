import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { EmailForwardingCard } from "./automation/EmailForwardingCard";
import { DeliveryRuntimeCard } from "./DeliveryRuntimeCard";
import { ScriptPipelineCard } from "./ScriptPipelineCard";

const getRuntimeStatus = vi.fn();
const testScript = vi.fn();

vi.mock("../../api/client", () => ({
  api: {
    getRuntimeStatus: (...args: unknown[]) => getRuntimeStatus(...args),
    testScript: (...args: unknown[]) => testScript(...args),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  getRuntimeStatus.mockResolvedValue({
    polling: {
      running: true,
      enabled: true,
      interval_seconds: 30,
      last_run: "",
      next_run: "",
      last_error: "",
    },
    deliveries: {
      pending: 0,
      sending: 0,
      sent: 7,
      failed: 0,
      skipped: 0,
      last_error: "",
      last_error_at: "",
    },
    pool: {
      enabled: true,
      api_key_configured: true,
      total: 5,
      available: 3,
      claimed: 2,
    },
  });
});

test("runtime card exposes live polling delivery and pool state", async () => {
  render(<DeliveryRuntimeCard />);

  expect(await screen.findByText("运行中 · 30s")).toBeInTheDocument();
  expect(screen.getByText("7 已发送 · 0 失败")).toBeInTheDocument();
  expect(screen.getByText("3/5 可领取")).toBeInTheDocument();
});

test("shell pipeline controls update settings and execute the configured path", async () => {
  const setSetting = vi.fn();
  testScript.mockResolvedValue({ success: true, message: "ok" });
  render(
    <ScriptPipelineCard
      settings={{
        script_notification_enabled: "false",
        script_notification_path: "/data/pipelines/new-mail.sh",
        script_notification_timeout: "15",
      }}
      setSetting={setSetting}
      isAdmin
    />,
  );

  fireEvent.click(screen.getByRole("checkbox", { name: "新邮件触发 .sh 流水线" }));
  fireEvent.click(screen.getByRole("button", { name: /测试执行/ }));

  expect(setSetting).toHaveBeenCalledWith("script_notification_enabled", "true");
  await waitFor(() => expect(testScript).toHaveBeenCalledWith("/data/pipelines/new-mail.sh", 15));
  expect(await screen.findByText("ok")).toBeInTheDocument();
});

test("email forwarding selects an existing account as the sender", async () => {
  const setSetting = vi.fn();
  render(
    <EmailForwardingCard
      settings={{ email_notification_account_id: "", email_notification_recipient: "" }}
      setSetting={setSetting}
      toast={vi.fn()}
      user={{ is_admin: true, username: "admin" }}
      accounts={[
        {
          id: 1,
          provider: "outlook",
          primary_address: "owner@example.com",
          display_name: "工作邮箱",
          status: "active",
          usable_emails: [
            {
              id: 1,
              address: "owner@example.com",
              label: "工作邮箱",
              kind: "primary",
              status: "active",
            },
          ],
        },
      ]}
    />,
  );

  fireEvent.click(screen.getByRole("combobox", { name: "发件账号" }));
  fireEvent.keyDown(await screen.findByRole("option", { name: /owner@example\.com/ }), {
    key: "Enter",
  });

  expect(setSetting).toHaveBeenCalledWith("email_notification_account_id", "1");

  fireEvent.change(screen.getByRole("textbox", { name: "转发到" }), {
    target: { value: "archive@example.com" },
  });
  expect(setSetting).toHaveBeenCalledWith("email_notification_recipient", "archive@example.com");
});
