import { request } from '../core'
import type {
  Overview,
  OverviewSummary,
  VerificationStats,
  PoolStats,
  ActivityStats
} from '../../types'

export const overviewApi = {
  overview: () => request<Overview>('/workbench/overview'),

  getOverviewSummary: () => request<OverviewSummary>('/overview/summary'),

  getVerificationStats: () => request<VerificationStats>('/overview/verification-stats'),

  getPoolStats: () => request<PoolStats>('/overview/pool-stats'),

  getActivityStats: () => request<ActivityStats>('/overview/activity'),

  exportData: () => request<unknown>('/data/export'),

  importData: (data: unknown) =>
    request<unknown>('/data/import', { method: 'POST', body: JSON.stringify(data) })
}
