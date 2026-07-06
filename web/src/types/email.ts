import type { Group, Tag } from "./group";

export type UsableEmailKind = "custom" | "primary" | "alias" | "temp";
export type UsableEmailStatus = "active" | "inactive" | "archived";

export interface UsableEmail {
  id: number;
  address: string;
  label: string;
  kind: UsableEmailKind;
  status: UsableEmailStatus;
  group?: Group | null;
  tags?: Tag[];
  platform_binding_count?: number;
  updated_at?: string;
  email_account_id?: number | null;
  provider?: string;
}

export interface WorkbenchEmail extends UsableEmail {
  platform_binding_count: number;
}

export interface PaginatedEmails {
  usable_emails: WorkbenchEmail[];
  total: number;
  page: number;
  page_size: number;
}

export interface SendDebugEmailRequest {
  recipient: string;
  subject: string;
  body: string;
}

export interface SendDebugEmailResult {
  success: boolean;
  code: string;
  message: string;
  credential_policy: string;
  credential_strategy: string;
  from_address: string;
  to_address: string;
  usable_email_id: number | null;
  email_account_id: number | null;
  smtp_host: string;
  smtp_port: number | null;
  security: string;
  actions: string[];
}
