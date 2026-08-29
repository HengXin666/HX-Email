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

export interface AccountStats {
  total: number;
  oauth: number;
  microsoft: number;
  google: number;
  valid: number;
  invalid: number;
  unknown: number;
  failed_refresh: number;
  last_refresh: string | null;
  by_provider: Array<{ provider: string; count: number }>;
  by_group: Array<{
    group_id: number;
    name: string;
    color: string;
    total: number;
    valid: number;
    invalid: number;
  }>;
  ungrouped: { total: number; valid: number; invalid: number };
  error_categories: Array<{
    provider: string;
    category: string;
    label: string;
    count: number;
  }>;
  age_buckets: Array<{
    label: string;
    min: number;
    max: number | null;
    valid: number;
    invalid: number;
    unknown: number;
  }>;
  daily_new: Array<{ date: string; count: number }>;
  daily_refresh: Array<{ date: string; success: number; failed: number }>;
  /** 每次巡航轮次的成败统计 (按时间升序): 用于「每次巡航成功率」趋势.
   *  仅含多账号批量巡航 (patrol all/failed/group), 已排除 single 手动单刷。 */
  refresh_rounds: Array<{
    round_id: number;
    started_at: string;
    scope: string;
    total: number;
    success: number;
    failed: number;
    success_rate: number;
  }>;
}
