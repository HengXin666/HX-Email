import type {
  AuthResponse,
  AccountImportResult,
  EmailAccount,
  TokenConfig,
  Group,
  MailPoolEntry,
  Overview,
  PaginatedEmails,
  Platform,
  PlatformBinding,
  Tag,
  TempMessage,
  UsableEmail,
  User,
  VerificationMatch,
  TokenExchangeResult,
  TokenPrepareResult,
  RefreshLog,
  InvalidTokenCandidate,
  RefreshStats,
  SSERefreshEvent
} from '../types'

let _sessionExpiredHandled = false

function getStoredToken(): string | null {
  try {
    return window.localStorage?.getItem('hx_token') ?? null
  } catch {
    return null
  }
}

function handleSessionExpired(): void {
  if (_sessionExpiredHandled) return
  _sessionExpiredHandled = true
  try {
    window.localStorage?.removeItem('hx_token')
    window.localStorage?.removeItem('hx_user')
    window.sessionStorage?.setItem('hx_session_expired', '1')
  } catch {}
  try {
    window.dispatchEvent(new CustomEvent('auth:session-expired'))
  } catch {}
}

export async function streamRefresh(
  url: string,
  body?: object,
  onProgress?: (e: SSERefreshEvent) => void
): Promise<void> {
  const token = getStoredToken()
  const res = await fetch(url, {
    method: body ? 'POST' : 'GET',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  })
  if (res.status === 401 && token) {
    handleSessionExpired()
    throw new Error('登录已过期，请重新登录')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '请求失败')
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data: SSERefreshEvent = JSON.parse(line.slice(6))
          onProgress?.(data)
        } catch { /* skip malformed SSE lines */ }
      }
    }
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string>)
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(path, { ...init, headers })
  if (res.status === 401 && token) {
    handleSessionExpired()
    throw new Error('登录已过期，请重新登录')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '请求失败')
  }
  if (res.status === 204) return null as T
  try {
    return await res.json()
  } catch {
    const text = await res.text().catch(() => '')
    throw new Error(`Invalid JSON response (status ${res.status}): ${text.slice(0, 200)}`)
  }
}

async function requestText(path: string, init: RequestInit = {}): Promise<string> {
  const token = getStoredToken()
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>)
  }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(path, { ...init, headers })
  if (res.status === 401 && token) {
    handleSessionExpired()
    throw new Error('登录已过期，请重新登录')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '请求失败')
  }
  return res.text()
}

// ========== Auth ==========
export const api = {
  login: (username: string, password: string) =>
    request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    }),
  register: (username: string, password: string) =>
    request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  updateCredentials: (username: string, password: string) =>
    request<{ user: User }>('/auth/me/credentials', {
      method: 'PUT',
      body: JSON.stringify({ username, password })
    }),

  // ========== Overview ==========
  overview: () => request<Overview>('/workbench/overview'),

  // ========== Groups ==========
  createGroup: (name: string, color = '#58a6ff') =>
    request<Group>('/groups', { method: 'POST', body: JSON.stringify({ name, color }) }),
  updateGroup: (id: number, name: string, color: string) =>
    request<Group>(`/groups/${id}`, { method: 'PUT', body: JSON.stringify({ name, color }) }),
  deleteGroup: (id: number) =>
    request<void>(`/groups/${id}`, { method: 'DELETE' }),
  listGroups: () => request<Group[]>('/groups'),

  // ========== Tags ==========
  createTag: (name: string, color = '#238636') =>
    request<Tag>('/tags', { method: 'POST', body: JSON.stringify({ name, color }) }),
  listTags: () => request<Tag[]>('/tags'),

  // ========== Usable Emails ==========
  listUsableEmails: () =>
    request<{ usable_emails: UsableEmail[] }>('/usable-emails').then((r) => r.usable_emails),
  getUsableEmail: (id: number) => request<UsableEmail>(`/usable-emails/${id}`),
  createUsableEmail: (address: string, label = '') =>
    request<UsableEmail>('/usable-emails', {
      method: 'POST',
      body: JSON.stringify({ address, label })
    }),
  organizeUsableEmail: (id: number, data: { label?: string | null; group_id?: number | null; tag_ids?: number[] }) =>
    request<UsableEmail>(`/usable-emails/${id}/organize`, {
      method: 'PUT',
      body: JSON.stringify(data)
    }),
  deactivateUsableEmail: (id: number) =>
    request<UsableEmail>(`/usable-emails/${id}/deactivate`, { method: 'POST' }),
  readVerification: (id: number) =>
    request<{ usable_email: UsableEmail; matches: VerificationMatch[] }>(
      `/usable-emails/${id}/verification/read`,
      { method: 'POST' }
    ),
  verificationHistory: (id: number) =>
    request<{ usable_email: UsableEmail; matches: VerificationMatch[] }>(
      `/usable-emails/${id}/verification/history`
    ),

  // Workbench paginated emails
  workbenchEmails: (params: Record<string, string | number | undefined> = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v !== undefined && qs.append(k, String(v)))
    return request<PaginatedEmails>(`/workbench/usable-emails?${qs.toString()}`)
  },

  // ========== Platforms ==========
  listPlatforms: () => request<{ platforms: Platform[] }>('/platforms').then((r) => r.platforms),
  createPlatform: (name: string) =>
    request<Platform>('/platforms', { method: 'POST', body: JSON.stringify({ name }) }),
  updatePlatform: (id: number, name: string) =>
    request<Platform>(`/platforms/${id}`, { method: 'PUT', body: JSON.stringify({ name }) }),
  deletePlatform: (id: number) =>
    request<void>(`/platforms/${id}`, { method: 'DELETE' }),
  listBindings: (emailId: number) =>
    request<{ platform_bindings: PlatformBinding[] }>(
      `/usable-emails/${emailId}/platform-bindings`
    ).then((r) => r.platform_bindings),
  createBinding: (emailId: number, platform_id: number, status = 'active', notes = '') =>
    request<PlatformBinding>(`/usable-emails/${emailId}/platform-bindings`, {
      method: 'POST',
      body: JSON.stringify({ platform_id, status, notes })
    }),
  updateBinding: (id: number, status: string, notes: string) =>
    request<PlatformBinding>(`/platform-bindings/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ status, notes })
    }),

  // ========== Email Accounts ==========
  listEmailAccounts: () =>
    request<{ email_accounts: EmailAccount[] }>('/email-accounts').then((r) => r.email_accounts),
  createEmailAccount: (data: {
    provider: string
    primary_address: string
    display_name: string
    alias_addresses?: string[]
  }) =>
    request<EmailAccount>('/email-accounts', { method: 'POST', body: JSON.stringify(data) }),
  addAlias: (accountId: number, address: string, label?: string) =>
    request<UsableEmail>(`/email-accounts/${accountId}/aliases`, {
      method: 'POST',
      body: JSON.stringify({ address, label })
    }),
  deactivateEmailAccount: (id: number) =>
    request<EmailAccount>(`/email-accounts/${id}/deactivate`, { method: 'POST' }),
  importEmailAccounts: (text: string, duplicate_strategy = 'skip') =>
    request<AccountImportResult>('/email-accounts/import', {
      method: 'POST',
      body: JSON.stringify({ text, duplicate_strategy })
    }),
  exportEmailAccountsText: () => requestText('/email-accounts/export-text'),

  // ========== Token Tool ==========
  getTokenToolConfig: () =>
    request<{ success: boolean; data: TokenConfig }>('/token-tool/config').then((r) => r.data),
  saveTokenToolConfig: (data: TokenConfig) =>
    request<{ success: boolean; data: TokenConfig }>('/token-tool/config', {
      method: 'POST',
      body: JSON.stringify(data)
    }).then((r) => r.data),
  listTokenToolAccounts: () =>
    request<{ success: boolean; data: Array<{ id: number; email: string; status: string }> }>(
      '/token-tool/accounts'
    ).then((r) => r.data),
  prepareTokenTool: (data: TokenConfig) =>
    request<{ success: boolean; data: TokenPrepareResult }>('/token-tool/prepare', {
      method: 'POST',
      body: JSON.stringify(data)
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
    request<{ success: boolean; data: { account_id: number; email: string } }>('/token-tool/save', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  // ========== Mail Pool ==========
  listPoolEntries: () =>
    request<{ entries: MailPoolEntry[] }>('/mail-pool/entries').then((r) => r.entries),
  addPoolEntry: (usable_email_id: number) =>
    request<MailPoolEntry>('/mail-pool/entries', {
      method: 'POST',
      body: JSON.stringify({ usable_email_id })
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

  // ========== Temp Mail ==========
  createTempMail: (label: string) =>
    request<UsableEmail>('/temp-mail/cf/mailboxes', {
      method: 'POST',
      body: JSON.stringify({ address: null, label })
    }),
  archiveTempMail: (id: number) =>
    request<UsableEmail>(`/temp-mail/${id}/archive`, { method: 'POST' }),
  tempMessages: (id: number) =>
    request<{ messages: TempMessage[] }>(`/temp-mail/${id}/messages`).then((r) => r.messages),
  tempCodes: (id: number) =>
    request<{ codes: Array<{ message_id: string; code: string }> }>(`/temp-mail/${id}/codes`).then(
      (r) => r.codes
    ),
  tempLinks: (id: number) =>
    request<{ links: Array<{ message_id: string; url: string }> }>(
      `/temp-mail/${id}/verification-links`
    ).then((r) => r.links),

  // ========== Settings ==========
  getSettings: () => request<Record<string, string>>('/settings'),
  updateSettings: (data: Record<string, unknown>) =>
    request<{ success: boolean }>('/settings', { method: 'PUT', body: JSON.stringify(data) }),
  validateCron: (cron: string) =>
    request<{ valid: boolean; message: string }>('/settings/validate-cron', {
      method: 'POST',
      body: JSON.stringify({ cron_expression: cron })
    }),
  testTelegram: (data: Record<string, unknown>) =>
    request<{ success: boolean; message: string }>('/settings/telegram-test', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
  testEmail: (data: Record<string, unknown>) =>
    request<{ success: boolean; message: string }>('/settings/email-test', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
  testWebhook: (data: Record<string, unknown>) =>
    request<{ success: boolean; message: string }>('/settings/webhook-test', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
  testVerificationAI: (data: Record<string, unknown>) =>
    request<{ success: boolean; code: string; message: string }>('/settings/verification-ai-test', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
  syncCFDomains: (data: Record<string, unknown>) =>
    request<{ success: boolean; domains: string[]; message: string }>(
      '/settings/cf-worker-sync-domains',
      { method: 'POST', body: JSON.stringify(data) }
    ),
  getAPIKeyPlaintext: () =>
    request<{ external_api_key: string }>('/settings/external-api-key/plaintext'),
  getVersionCheck: () =>
    request<{ current_version: string; latest_version?: string; has_update: boolean }>(
      '/system/version-check'
    ),
  getDeploymentInfo: () =>
    request<{ python_version: string; platform: string }>('/system/deployment-info'),
  triggerUpdate: () =>
    request<{ success: boolean; message: string }>('/system/trigger-update', { method: 'POST' }),
  testWatchtower: () =>
    request<{ success: boolean; message: string }>('/system/test-watchtower', { method: 'POST' }),
  reloadPlugins: () =>
    request<{ success: boolean; message: string }>('/system/reload-plugins', { method: 'POST' }),

  // ========== Token Refresh ==========
  refreshAccount: (id: number) =>
    request<{ success: boolean; message: string; account_id: number; email: string; status: string }>(
      `/email-accounts/${id}/refresh`,
      { method: 'POST' }
    ),
  retryRefreshAccount: (id: number) =>
    request<{ success: boolean; message: string }>(
      `/email-accounts/${id}/retry-refresh`,
      { method: 'POST' }
    ),

  // ========== Refresh Logs ==========
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
  getRefreshStats: () =>
    request<RefreshStats>('/email-accounts/refresh-stats'),

  // ========== Data ==========
  exportData: () => request<unknown>('/data/export'),
  importData: (data: unknown) =>
    request<unknown>('/data/import', { method: 'POST', body: JSON.stringify(data) })
}
