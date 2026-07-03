export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  action: string;
  resource_type: string;
  resource_id: number | null;
  detail: string;
  ip_address: string;
  created_at: string;
}
