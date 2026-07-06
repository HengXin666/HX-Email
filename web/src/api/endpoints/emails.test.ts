import { afterEach, expect, test, vi } from "vitest";

import { emailsApi } from "./emails";

afterEach(() => {
  vi.restoreAllMocks();
});

test("getEmailAccount returns credentials from the account detail response", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json({
        id: 7,
        provider: "outlook",
        primary_address: "owner@outlook.com",
        display_name: "Owner",
        status: "active",
        client_id: "client-id-from-db",
        refresh_token: "refresh-token-from-db",
        usable_emails: [],
      }),
    ),
  );

  const account = await emailsApi.getEmailAccount(7);

  expect(account.client_id).toBe("client-id-from-db");
  expect(account.refresh_token).toBe("refresh-token-from-db");
});

test("network fetch failures use a stable user-facing message", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("NetworkError when attempting to fetch resource.");
    }),
  );

  await expect(emailsApi.listEmailAccounts()).rejects.toThrow(
    "无法连接服务器，请确认后端服务已启动并且网络连接正常",
  );
});

test("sendDebugEmail posts to the selected usable email route", async () => {
  const fetchMock = vi.fn(async () =>
    Response.json({
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
    }),
  );
  vi.stubGlobal("fetch", fetchMock);

  const result = await emailsApi.sendDebugEmail(12, {
    recipient: "receiver@example.com",
    subject: "Debug",
    body: "Hello",
  });

  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/usable-emails/12/send-debug-email",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        recipient: "receiver@example.com",
        subject: "Debug",
        body: "Hello",
      }),
    }),
  );
  expect(result.code).toBe("sent");
});
