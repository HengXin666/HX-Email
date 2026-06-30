import type { TempMessage, UsableEmail } from "../../types";
import { request } from "../core";

export const tempMailApi = {
  createTempMail: (label: string) =>
    request<UsableEmail>("/temp-mail/cf/mailboxes", {
      method: "POST",
      body: JSON.stringify({ address: null, label }),
    }),

  archiveTempMail: (id: number) =>
    request<UsableEmail>(`/temp-mail/${id}/archive`, { method: "POST" }),

  tempMessages: (id: number) =>
    request<{ messages: TempMessage[] }>(`/temp-mail/${id}/messages`).then((r) => r.messages),

  tempCodes: (id: number) =>
    request<{ codes: Array<{ message_id: string; code: string }> }>(`/temp-mail/${id}/codes`).then(
      (r) => r.codes,
    ),

  tempLinks: (id: number) =>
    request<{ links: Array<{ message_id: string; url: string }> }>(
      `/temp-mail/${id}/verification-links`,
    ).then((r) => r.links),
};
