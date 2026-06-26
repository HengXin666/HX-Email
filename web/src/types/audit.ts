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
