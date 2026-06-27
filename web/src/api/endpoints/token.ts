import { request } from '../core'
import type {
  TokenConfig,
  TokenPrepareResult,
  TokenExchangeResult
} from '../../types'

export const tokenApi = {
  getTokenToolConfig: () =>
    request<{ success: boolean; data: TokenConfig }>('/token-tool/config').then((r) => r.data),

  saveTokenToolConfig: (data: TokenConfig) =>
    request<{ success: boolean; data: TokenConfig }>('/token-tool/config', {
      method: 'POST',
      body: JSON.stringify(data)
    }).then((r) => r.data),

  listTokenToolAccounts: () =>
    request<{
      success: boolean
      data: Array<{ id: number; email: string; status: string }>
    }>('/token-tool/accounts').then((r) => r.data),

  prepareTokenTool: (data: TokenConfig) =>
    request<{ success: boolean; data: TokenPrepareResult }>('/token-tool/prepare', {
      method: 'POST',
      body: JSON.stringify(data)
    }).then((r) => r.data),

  prepareTokenToolFromConfig: () =>
    request<{ success: boolean; data: TokenPrepareResult }>('/token-tool/prepare-from-config', {
      method: 'POST'
    }).then((r) => r.data),

  exchangeTokenTool: (data: { code?: string; state?: string; callback_url?: string }) =>
    request<{ success: boolean; data: TokenExchangeResult }>('/token-tool/exchange', {
      method: 'POST',
      body: JSON.stringify(data)
    }).then((r) => r.data),

  saveTokenTool: (data: {
    mode: 'create' | 'update'
    account_id?: number | null
    email?: string
    client_id: string
    refresh_token: string
  }) =>
    request<{ success: boolean; data: { account_id: number; email: string } }>(
      '/token-tool/save',
      { method: 'POST', body: JSON.stringify(data) }
    )
}
