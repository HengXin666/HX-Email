import { request, requestText } from '../core'
import type {
  UsableEmail,
  VerificationMatch,
  PaginatedEmails,
  EmailAccount,
  AccountImportResult
} from '../../types'

export const emailsApi = {
  // Usable Emails
  listUsableEmails: () =>
    request<{ usable_emails: UsableEmail[] }>('/usable-emails').then((r) => r.usable_emails),

  getUsableEmail: (id: number) => request<UsableEmail>(`/usable-emails/${id}`),

  createUsableEmail: (address: string, label = '') =>
    request<UsableEmail>('/usable-emails', {
      method: 'POST',
      body: JSON.stringify({ address, label })
    }),

  organizeUsableEmail: (
    id: number,
    data: { label?: string | null; group_id?: number | null; tag_ids?: number[] }
  ) =>
    request<UsableEmail>(`/usable-emails/${id}/organize`, {
      method: 'PUT',
      body: JSON.stringify(data)
    }),

  deactivateUsableEmail: (id: number) =>
    request<UsableEmail>(`/usable-emails/${id}/deactivate`, { method: 'POST' }),

  deleteUsableEmail: (id: number) =>
    request<{ success: boolean; message: string }>(`/usable-emails/${id}`, { method: 'DELETE' }),

  activateUsableEmail: (id: number) =>
    request<{ usable_email: UsableEmail }>(`/usable-emails/${id}/activate`, { method: 'POST' }),

  // Verification
  readVerification: (id: number) =>
    request<{ usable_email: UsableEmail; matches: VerificationMatch[] }>(
      `/usable-emails/${id}/verification/read`,
      { method: 'POST' }
    ),

  verificationHistory: (id: number) =>
    request<{ usable_email: UsableEmail; matches: VerificationMatch[] }>(
      `/usable-emails/${id}/verification/history`
    ),

  verificationState: (id: number) =>
    request<{
      last_extracted_at: string | null
      seen_codes: string[]
      message_count: number
    }>(`/usable-emails/${id}/verification/state`),

  // Workbench
  workbenchEmails: (params: Record<string, string | number | undefined> = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(
      ([k, v]) => v !== undefined && qs.append(k, String(v))
    )
    return request<PaginatedEmails>(`/workbench/usable-emails?${qs.toString()}`)
  },

  // Messages
  getMessages: (emailId: number, limit = 100, offset = 0) =>
    request<{
      messages: Array<{
        id: number
        from_address: string
        recipient_address: string
        subject: string
        body: string
        received_at: string
        created_at: string
      }>
      total: number
    }>(`/usable-emails/${emailId}/messages?limit=${limit}&offset=${offset}`).then((r) => r.messages),

  fetchEmails: (emailId: number) =>
    request<{
      account_id: number
      email: string
      messages_stored: number
      codes_found: number
      error: string
    }>(`/usable-emails/${emailId}/fetch-emails`, { method: 'POST' }),

  // Email Accounts
  listEmailAccounts: () =>
    request<{ accounts: EmailAccount[] }>('/email-accounts').then((r) => r.accounts),

  createEmailAccount: (data: {
    provider: string
    primary_address: string
    display_name: string
    alias_addresses?: string[]
  }) => request<EmailAccount>('/email-accounts', { method: 'POST', body: JSON.stringify(data) }),

  addAlias: (accountId: number, address: string, label?: string) =>
    request<UsableEmail>(`/email-accounts/${accountId}/aliases`, {
      method: 'POST',
      body: JSON.stringify({ address, label })
    }),

  getEmailAccount: (id: number) =>
    request<{
      account: EmailAccount & {
        password?: string
        refresh_token?: string
        has_password?: boolean
        has_refresh_token?: boolean
      }
    }>(`/email-accounts/${id}`).then((r) => r.account),

  deactivateEmailAccount: (id: number) =>
    request<EmailAccount>(`/email-accounts/${id}/deactivate`, { method: 'POST' }),

  deleteEmailAccount: (id: number) =>
    request<{ success: boolean }>(`/email-accounts/${id}`, { method: 'DELETE' }),

  updateEmailAccount: (
    id: number,
    data: {
      email?: string | null
      password?: string | null
      client_id?: string | null
      refresh_token?: string | null
      group_id?: number | null
      remark?: string | null
      status?: string | null
      provider?: string | null
      imap_host?: string | null
      imap_port?: number | null
    }
  ) => request<EmailAccount>(`/email-accounts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  importEmailAccounts: (
    text: string,
    options?: {
      duplicate_strategy?: string
      provider?: string
      group_id?: number | null
      add_to_pool?: boolean
      custom_imap_host?: string
      custom_imap_port?: number
    }
  ) =>
    request<AccountImportResult>('/email-accounts/import', {
      method: 'POST',
      body: JSON.stringify({
        text,
        duplicate_strategy: options?.duplicate_strategy ?? 'skip',
        provider: options?.provider ?? 'outlook',
        group_id: options?.group_id ?? null,
        add_to_pool: options?.add_to_pool ?? false,
        custom_imap_host: options?.custom_imap_host ?? '',
        custom_imap_port: options?.custom_imap_port ?? 993
      })
    }),

  listProviders: () =>
    request<{
      success: boolean
      providers: Array<{ key: string; label: string; imap_host: string; imap_port: number }>
    }>('/email-accounts/providers').then((r) => r.providers),

  exportEmailAccountsText: () => requestText('/email-accounts/export-text')
}
