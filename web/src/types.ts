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
  primary_usable_email?: UsableEmail
  usable_emails: UsableEmail[]
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
