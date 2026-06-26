import { request } from '../core'
import type { RefreshLog, InvalidTokenCandidate, RefreshStats } from '../../types'

export const refreshApi = {
  refreshAccount: (id: number) =>
    request<{
      success: boolean
      message: string
      account_id: number
      email: string
      status: string
    }>(`/email-accounts/${id}/refresh`, { method: 'POST' }),

  retryRefreshAccount: (id: number) =>
    request<{ success: boolean; message: string }>(
      `/email-accounts/${id}/retry-refresh`,
      { method: 'POST' }
    ),

  getRefreshLogs: (limit = 200, offset = 0) =>
    request<{ logs: RefreshLog[]; total: number }>(
      `/email-accounts/refresh-logs?limit=${limit}&offset=${offset}`
    ),

  getAccountRefreshLogs: (id: number, limit = 100, offset = 0) =>
    request<{ logs: RefreshLog[] }>(
      `/email-accounts/${id}/refresh-logs?limit=${limit}&offset=${offset}`
    ),

  getFailedRefreshLogs: () =>
    request<{ logs: RefreshLog[] }>('/email-accounts/refresh-logs/failed'),

  getInvalidTokenCandidates: (limit = 50, offset = 0) =>
    request<{ candidates: InvalidTokenCandidate[] }>(
      `/email-accounts/invalid-token-candidates?limit=${limit}&offset=${offset}`
    ),

  getRefreshStats: () => request<RefreshStats>('/email-accounts/refresh-stats')
}
