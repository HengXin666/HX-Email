// Re-export all types from domain-specific modules (backward-compatible barrel)
export type { User, AuthResponse } from './types/auth'
export type { Group, Tag } from './types/group'
export type {
  UsableEmailKind,
  UsableEmailStatus,
  UsableEmail,
  WorkbenchEmail,
  PaginatedEmails
} from './types/email'
export type { Platform, BindingStatus, PlatformBinding } from './types/platform'
export type {
  EmailAccount,
  AccountImportResult,
  TokenConfig,
  TokenPrepareResult,
  TokenExchangeResult
} from './types/account'
export type {
  MailPoolStatus,
  MailPoolEntry,
  PoolAdminAccount,
  PoolStats
} from './types/pool'
export type { TempMessage, VerificationMatch } from './types/message'
export type {
  Overview,
  OverviewSummary,
  VerificationStats,
  ActivityStats
} from './types/overview'
export type {
  RefreshLog,
  InvalidTokenCandidate,
  RefreshStats,
  SSERefreshEvent
} from './types/refresh'
export type { AuditLogEntry } from './types/audit'
export type { Pagination } from './types/common'
