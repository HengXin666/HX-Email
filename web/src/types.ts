// 类型定义 - 与 HX-Email API 对齐

export interface User {
  id: number
  username: string
  is_admin: boolean
}

export interface AuthResponse {
  access_token: string
  user: User
}

export interface Group {
  id: number
  name: string
  color: string
  count?: number // 客户端计算的内部数量
}

export interface Tag {
  id: number
  name: string
  color: string
}

export type UsableEmailKind = 'custom' | 'primary' | 'alias' | 'temp'
export type UsableEmailStatus = 'active' | 'inactive' | 'archived'

export interface UsableEmail {
  id: number
  address: string
  label: string
  kind: UsableEmailKind
  status: UsableEmailStatus
  group?: Group | null
  tags?: Tag[]
  platform_binding_count?: number
  // 本地扩展字段
  updated_at?: string
  email_account_id?: number | null
  provider?: string
}

export interface Platform {
  id: number
  name: string
  binding_count?: number
}

export type BindingStatus =
  | 'active'
  | 'pending_verification'
  | 'risk'
  | 'disabled'
  | 'archived'

export interface PlatformBinding {
  id: number
  usable_email_id: number
  platform: Platform
  status: BindingStatus
  notes: string
}

export interface EmailAccount {
  id: number
  provider: string
  primary_address: string
  display_name: string
  status: 'active' | 'inactive'
  imap_host?: string
  imap_port?: number | null
  username?: string
  client_id?: string
  has_imap_password?: boolean
  has_refresh_token?: boolean
  remark?: string | null
  in_pool?: boolean
  primary_usable_email?: UsableEmail
  usable_emails: UsableEmail[]
  last_refresh_at?: string | null
  last_refresh_status?: string | null
}

export interface AccountImportResult {
  imported: number
  skipped: number
  failed: number
  errors: Array<{ line: number; email?: string; error: string }>
  errors_total: number
  duplicate_strategy: string
}

export interface TokenPrepareResult {
  authorize_url: string
  authorization_url: string
  state: string
  scope: string
}

export interface TokenConfig {
  client_id: string
  redirect_uri: string
  scope: string
  tenant: string
  prompt_consent: boolean
}

export interface TokenExchangeResult {
  client_id: string
  refresh_token: string
  access_token: string
  expires_in: number
  token_type: string
  granted_scope: string
  requested_scope: string
}

export type MailPoolStatus = 'available' | 'claimed' | 'completed' | 'cooling'

export interface MailPoolEntry {
  id: number
  usable_email: UsableEmail
  status: MailPoolStatus
  claim_key: string
  claimed_project_key: string
  completed_project_key: string
}

export interface TempMessage {
  id: string
  from_address: string
  subject: string
  text: string
  html?: string
  received_at?: string
}

export interface VerificationMatch {
  code: string | null
  link: string | null
  recipient_address: string
  certainty: 'high' | 'medium' | 'low'
  subject: string
  received_at?: string
}

export interface Overview {
  usable_email_count: number
  active_email_count: number
  account_count: number
  temp_email_count: number
  platform_count: number
  binding_count: number
  pool_available_count: number
  pool_claimed_count: number
  verification_count: number
}

export interface WorkbenchEmail extends UsableEmail {
  platform_binding_count: number
}

export interface PaginatedEmails {
  usable_emails: WorkbenchEmail[]
  total: number
  page: number
  page_size: number
}

export interface RefreshLog {
  id: number
  account_id: number
  email: string
  status: 'pending' | 'success' | 'failed'
  message: string
  error_detail: string
  started_at: string
  completed_at: string
  created_at: string
}

export interface InvalidTokenCandidate {
  account_id: number
  email: string
  error_detail: string
  last_failed_at: string
}

export interface RefreshStats {
  total: number
  success: number
  failed: number
  pending: number
  last_refresh: string
}

export interface SSERefreshEvent {
  type: 'progress' | 'complete'
  current?: number
  total?: number
  email?: string
  status?: string
  success?: number
  failed?: number
}

export interface PoolAdminAccount {
  id: number
  email: string
  provider: string
  pool_status: string
  group_name: string
  claimed_by: string
  claimed_at: string
  status: string
}

export interface Pagination {
  page: number
  page_size: number
  total_count: number
  total_pages: number
}

export interface AuditLogEntry {
  id: number
  user_id: number
  action: string
  resource_type: string
  resource_id: number
  detail: string
  ip_address: string
  created_at: string
}

export interface OverviewSummary {
  total_accounts: number
  active_accounts: number
  total_emails: number
  active_emails: number
  temp_emails: number
  platforms: number
  bindings: number
  pool_available: number
  pool_claimed: number
  pool_completed: number
  pool_cooling: number
  verification_total: number
}

export interface VerificationStats {
  total_extractions: number
  success_rate: number
  ai_fallback_count: number
  today_extractions: number
}

export interface PoolStats {
  available: number
  claimed: number
  completed: number
  cooling: number
  frozen: number
  retired: number
  total: number
}

export interface ActivityStats {
  recent_actions: Array<{ action: string; count: number }>
  today_actions: number
  total_actions: number
}
