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
