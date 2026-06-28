import { afterEach, expect, test, vi } from 'vitest'

import { emailsApi } from './emails'

afterEach(() => {
  vi.restoreAllMocks()
})

test('getEmailAccount returns credentials from the account detail response', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      Response.json({
        id: 7,
        provider: 'outlook',
        primary_address: 'owner@outlook.com',
        display_name: 'Owner',
        status: 'active',
        client_id: 'client-id-from-db',
        refresh_token: 'refresh-token-from-db',
        usable_emails: [],
      }),
    ),
  )

  const account = await emailsApi.getEmailAccount(7)

  expect(account.client_id).toBe('client-id-from-db')
  expect(account.refresh_token).toBe('refresh-token-from-db')
})
