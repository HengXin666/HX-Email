import { request } from '../core'
import type { MailPoolEntry, PoolAdminAccount, Pagination } from '../../types'

export const poolApi = {
  listPoolEntries: () =>
    request<{ entries: MailPoolEntry[] }>('/mail-pool/entries').then((r) => r.entries),

  addPoolEntry: (usable_email_id: number) =>
    request<MailPoolEntry>('/mail-pool/entries', {
      method: 'POST',
      body: JSON.stringify({ usable_email_id })
    }),

  removePoolEntry: (usable_email_id: number) =>
    request<null>(`/mail-pool/entries/${usable_email_id}`, {
      method: 'DELETE'
    }),

  claimPool: (project_key: string) =>
    request<MailPoolEntry>('/mail-pool/claim', {
      method: 'POST',
      body: JSON.stringify({ project_key })
    }),

  releasePool: (id: number) =>
    request<MailPoolEntry>(`/mail-pool/entries/${id}/release`, { method: 'POST' }),

  completePool: (id: number, project_key: string) =>
    request<MailPoolEntry>(`/mail-pool/entries/${id}/complete`, {
      method: 'POST',
      body: JSON.stringify({ project_key })
    }),

  cooldownPool: (id: number) =>
    request<MailPoolEntry>(`/mail-pool/entries/${id}/cooldown`, { method: 'POST' }),

  // Pool Admin
  listPoolAdminAccounts: (params: Record<string, string | number>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(
      ([k, v]) => v !== undefined && qs.append(k, String(v))
    )
    return request<{ accounts: PoolAdminAccount[]; pagination: Pagination }>(
      `/pool-admin/accounts?${qs}`
    )
  },

  executePoolAction: (accountId: number, action: string, extra?: Record<string, unknown>) =>
    request<{ success: boolean; message: string }>(
      `/pool-admin/accounts/${accountId}/action`,
      { method: 'POST', body: JSON.stringify({ action, ...extra }) }
    )
}
