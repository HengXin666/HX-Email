// Re-export all types from domain-specific modules (backward-compatible barrel)

export type {
  AccountImportResult,
  EmailAccount,
  GoogleOAuthConfig,
  GoogleOAuthPrepareResult,
  TokenConfig,
  TokenExchangeResult,
  TokenPrepareResult,
} from "./types/account";
export type { AuditLogEntry } from "./types/audit";
export type { AuthResponse, User } from "./types/auth";
export type { Pagination } from "./types/common";
export type {
  PaginatedEmails,
  SendDebugEmailRequest,
  SendDebugEmailResult,
  UsableEmail,
  UsableEmailKind,
  UsableEmailStatus,
  WorkbenchEmail,
} from "./types/email";
export type { Group, Tag } from "./types/group";
export type {
  EmailMessagesPage,
  StoredEmailMessage,
  TempMessage,
  VerificationMatch,
  VerificationReading,
} from "./types/message";
export type {
  ActivityStats,
  Overview,
  OverviewSummary,
  VerificationStats,
} from "./types/overview";
export type { BindingStatus, Platform, PlatformBinding } from "./types/platform";
export type {
  MailPoolEntry,
  MailPoolStatus,
  PoolAdminAccount,
  PoolStats,
} from "./types/pool";
export type {
  InvalidTokenCandidate,
  RefreshLog,
  RefreshStats,
  SSERefreshEvent,
} from "./types/refresh";
