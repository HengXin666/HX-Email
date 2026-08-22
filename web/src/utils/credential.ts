import type { EmailAccount } from "../types";

/** 凭证状态: valid=已通过至少一次刷新校验, invalid=最近刷新失败, none=无凭证/未刷新过 */
export type CredentialState = "valid" | "invalid" | "none";

export function accountCredentialState(account: EmailAccount | undefined): CredentialState {
  if (!account) return "none";
  const hasCredential: boolean =
    !!account.has_refresh_token || !!account.has_imap_password || !!account.imap_password;
  if (!hasCredential) return "none";
  if (account.refresh_failed_at) return "invalid";
  if (account.last_refresh_at) return "valid";
  return "none";
}
