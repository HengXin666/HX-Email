import { request } from '../core'
import type { AuditLogEntry } from '../../types'

export const auditApi = {
  getAuditLogs: (params: Record<string, string | number>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(
      ([k, v]) => v !== undefined && qs.append(k, String(v))
    )
    return request<{ logs: AuditLogEntry[]; total: number }>(`/audit-logs?${qs}`)
  }
}
