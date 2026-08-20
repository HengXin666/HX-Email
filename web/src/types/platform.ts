export interface Platform {
  id: number;
  name: string;
  binding_count?: number;
}

export type BindingStatus = "active" | "pending_verification" | "risk" | "disabled" | "archived";

export interface PlatformBinding {
  id: number;
  usable_email_id: number;
  platform: Platform;
  status: BindingStatus;
  notes: string;
}

export type RuleMatchField = "from" | "domain" | "subject" | "body";
export type RuleMatchType = "contains" | "exact" | "regex";

export interface PlatformRule {
  id: number;
  user_id: number;
  name: string;
  match_field: RuleMatchField;
  match_type: RuleMatchType;
  pattern: string;
  platform_name: string;
  enabled: boolean;
}

export interface PlatformScanItem {
  platform: string;
  source: string;
  senders: string[];
  sender_count: number;
  message_count: number;
  usable_email_ids: number[];
  first_seen: string;
  last_seen: string;
}

export interface ScanAcceptResult {
  platform: string;
  platform_id: number;
  bindings_created: number;
  bindings_skipped: number;
}
