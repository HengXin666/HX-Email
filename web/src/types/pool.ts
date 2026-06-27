import type { UsableEmail } from './email'

export type MailPoolStatus = 'available' | 'claimed' | 'completed' | 'cooling'

export interface MailPoolEntry {
  id: number
  usable_email: UsableEmail
  status: MailPoolStatus
  claim_key: string
  claimed_project_key: string
  completed_project_key: string
}

export interface PoolAdminAccount {
  id: number
  usable_email_id: number
  entry_id: number
  email: string
  provider: string
  pool_status: string
  group_name: string
  claimed_by: string
  claimed_at: string
  status: string
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
