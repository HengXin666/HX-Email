import type { EmailAccount } from "../types";

/** 凭证状态: valid=已通过至少一次刷新校验, invalid=最近刷新失败, none=无凭证/未刷新过 */
export type CredentialState = "valid" | "invalid" | "none";

/** OAuth 提供商 (refresh token 凭证), 与后端 patrol 索引口径一致 */
const OAUTH_PROVIDERS: readonly string[] = ["outlook", "gmail"];

export function isOAuthProvider(provider: string | undefined): boolean {
  return !!provider && OAUTH_PROVIDERS.includes(provider.toLowerCase());
}

export function accountCredentialState(account: EmailAccount | undefined): CredentialState {
  if (!account) return "none";
  const hasCredential: boolean =
    !!account.has_refresh_token || !!account.has_imap_password || !!account.imap_password;
  if (!hasCredential) return "none";
  if (account.refresh_failed_at) return "invalid";
  if (account.last_refresh_at) return "valid";
  return "none";
}

/** 账号存活天数 (基于初次导入时间 created_at); 解析失败返回 null */
export function accountAgeDays(account: EmailAccount): number | null {
  if (!account.created_at) return null;
  const created: number = Date.parse(account.created_at);
  if (Number.isNaN(created)) return null;
  return Math.max(0, Math.floor((Date.now() - created) / 86400000));
}
