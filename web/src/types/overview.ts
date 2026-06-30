export interface Overview {
  usable_email_count: number;
  active_email_count: number;
  account_count: number;
  temp_email_count: number;
  platform_count: number;
  binding_count: number;
  pool_available_count: number;
  pool_claimed_count: number;
  verification_count: number;
}

export interface OverviewSummary {
  total_accounts: number;
  active_accounts: number;
  total_emails: number;
  active_emails: number;
  temp_emails: number;
  platforms: number;
  bindings: number;
  pool_available: number;
  pool_claimed: number;
  pool_completed: number;
  pool_cooling: number;
  verification_total: number;
}

export interface VerificationStats {
  total_extractions: number;
  success_rate: number;
  ai_fallback_count: number;
  today_extractions: number;
}

export interface ActivityStats {
  recent_actions: Array<{ action: string; count: number }>;
  today_actions: number;
  total_actions: number;
}
