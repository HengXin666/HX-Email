import type { Group, Tag } from './group'

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
  updated_at?: string
  email_account_id?: number | null
  provider?: string
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
