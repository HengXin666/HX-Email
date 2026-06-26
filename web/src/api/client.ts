// Backward-compatible API barrel — assembles all endpoint modules into a single `api` object.
// Pages can continue to `import { api } from '../api/client'` without changes.

export { streamRefresh } from './core'

import { authApi } from './endpoints/auth'
import { groupsApi } from './endpoints/groups'
import { emailsApi } from './endpoints/emails'
import { platformsApi } from './endpoints/platforms'
import { poolApi } from './endpoints/pool'
import { tokenApi } from './endpoints/token'
import { tempMailApi } from './endpoints/temp-mail'
import { refreshApi } from './endpoints/refresh'
import { settingsApi } from './endpoints/settings'
import { auditApi } from './endpoints/audit'
import { overviewApi } from './endpoints/overview'

export const api = {
  ...authApi,
  ...overviewApi,
  ...groupsApi,
  ...emailsApi,
  ...platformsApi,
  ...poolApi,
  ...tokenApi,
  ...tempMailApi,
  ...refreshApi,
  ...settingsApi,
  ...auditApi
}
