// Backward-compatible API barrel — assembles all endpoint modules into a single `api` object.
// Pages can continue to `import { api } from '../api/client'` without changes.

export { streamRefresh } from "./core";

import { auditApi } from "./endpoints/audit";
import { authApi } from "./endpoints/auth";
import { emailsApi } from "./endpoints/emails";
import { groupsApi } from "./endpoints/groups";
import { overviewApi } from "./endpoints/overview";
import { platformsApi } from "./endpoints/platforms";
import { poolApi } from "./endpoints/pool";
import { refreshApi } from "./endpoints/refresh";
import { settingsApi } from "./endpoints/settings";
import { tempMailApi } from "./endpoints/temp-mail";
import { tokenApi } from "./endpoints/token";

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
  ...auditApi,
};
