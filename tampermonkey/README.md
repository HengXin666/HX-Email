# tampermonkey — HX-Email Microsoft App CLI

Monkey userscript folder for configuring / reusing the Azure App Registration
that HX-Email Token Tool needs for Outlook personal accounts.

## Files

| File                             | Purpose                                                                    |
| -------------------------------- | -------------------------------------------------------------------------- |
| `hx-email-azure-app-cli.user.js` | Tampermonkey script: floating panel on Azure portal + localhost Token Tool |
| `KEYS.md`                        | Copy-ready Client ID / redirect / scope for HX-Email                       |
| `azure-app.json`                 | Machine-readable app summary                                               |
| `compat-check.mjs`               | Local check that baked-in values match HX-Email defaults                   |

## What was configured in Azure (this session)

App name: **HX-Email**

| Item                | Value                                                        |
| ------------------- | ------------------------------------------------------------ |
| Client ID           | `75b83d3c-e645-464d-beac-c7e7c322f9b0`                       |
| Object ID           | `e5bd6035-bd08-4436-9a01-6dc9a8c991e6`                       |
| Tenant ID           | `03d895d4-b066-4a54-8433-56395b17b8ef`                       |
| Audience            | AzureADandPersonalMicrosoftAccount                           |
| Public client flows | Enabled                                                      |
| Redirect URI        | `http://localhost:8000/token-tool/callback` (Mobile/Desktop) |
| Graph delegated     | `Mail.Read`, `Mail.Send`, `offline_access`, `User.Read`      |

## HX-Email Token Tool steps after install

1. Open HX-Email → Token Tool → Microsoft.
2. Paste:
   - Client ID
   - Redirect URI (`http://localhost:8000/token-tool/callback` or your origin + `/token-tool/callback` if different)
   - Scope preset **Graph 邮件**
   - Tenant stays `consumers`
3. Save config → Prepare authorize URL → user consents → paste callback URL → exchange → save account.
4. Send mail path requires Graph `Mail.Send` (already on this app). Old refresh tokens without Send must re-consent.

## Userscript usage

1. Install Tampermonkey.
2. Import / paste `hx-email-azure-app-cli.user.js`.
3. Visit Azure portal or `http://localhost:8000/...`.
4. Panel actions:
   - Copy Client ID / Redirect / Scope / full key block / Token Tool JSON
   - Jump to App Overview / Authentication / API permissions
   - On localhost: attempt fill Token Tool form fields

## Compat check

```bash
node tampermonkey/compat-check.mjs
```

Exit 0 means baked-in scope/redirect match HX-Email server + web defaults.

## Boundary

- Only files under `tampermonkey/` are maintained for this feature.
- Script does not store Microsoft passwords or refresh tokens.
- First-time user consent still happens in the Microsoft login UI.
