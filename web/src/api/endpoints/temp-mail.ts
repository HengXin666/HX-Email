import type { TempCode, TempMessage, UsableEmail } from "../../types";
import { request } from "../core";

const TEMP_MAIL_REQUEST_OPTIONS: RequestInit = { cache: "no-store" };

export const tempMailApi = {
  createTempMail: (label: string) =>
    request<UsableEmail>("/temp-mail/cf/mailboxes", {
      method: "POST",
      body: JSON.stringify({ address: null, label }),
    }),

  archiveTempMail: (id: number) =>
    request<UsableEmail>(`/temp-mail/${id}/archive`, { method: "POST" }),

  tempMessages: (id: number) =>
    request<{ messages: TempMessage[] }>(
      `/temp-mail/${id}/messages`,
      TEMP_MAIL_REQUEST_OPTIONS,
    ).then((r) => r.messages),

  tempCodes: (id: number) =>
    request<{ codes: TempCode[] }>(`/temp-mail/${id}/codes`, TEMP_MAIL_REQUEST_OPTIONS).then(
      (r) => r.codes,
    ),

  tempLinks: (id: number) =>
    request<{ links: Array<{ message_id: string; url: string }> }>(
      `/temp-mail/${id}/verification-links`,
      TEMP_MAIL_REQUEST_OPTIONS,
    ).then((r) => r.links),
};
