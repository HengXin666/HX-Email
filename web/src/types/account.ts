import type { UsableEmail } from "./email";

export interface EmailAccount {
  id: number;
  provider: string;
  primary_address: string;
  display_name: string;
  status: "active" | "inactive";
  imap_host?: string;
  imap_port?: number | null;
  username?: string;
  imap_password?: string;
  client_id?: string;
  refresh_token?: string;
  has_imap_password?: boolean;
  has_refresh_token?: boolean;
  group_id?: number | null;
  remark?: string | null;
  telegram_enabled?: boolean;
  in_pool?: boolean;
  primary_usable_email?: UsableEmail;
  usable_emails: UsableEmail[];
  last_refresh_at?: string | null;
  last_refresh_status?: string | null;
}

export interface AccountImportResult {
  imported: number;
  skipped: number;
  failed: number;
  errors: Array<{ line: number; email?: string; error: string }>;
  errors_total: number;
  duplicate_strategy: string;
}

export interface TokenConfig {
  client_id: string;
  redirect_uri: string;
  scope: string;
  tenant: string;
  prompt_consent: boolean;
}

export interface TokenPrepareResult {
  authorize_url: string;
  authorization_url: string;
  state: string;
  scope: string;
}

export interface TokenExchangeResult {
  client_id: string;
  refresh_token: string;
  access_token: string;
  expires_in: number;
  token_type: string;
  granted_scope: string;
  requested_scope: string;
}

export interface GoogleOAuthConfig {
  client_id: string;
  redirect_uri: string;
  has_client_secret: boolean;
}

export interface GoogleOAuthPrepareResult {
  authorization_url: string;
  state: string;
}
