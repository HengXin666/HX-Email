# tampermonkey — HX-Email 油猴脚本集

Monkey userscripts folder for HX-Email related Google / Microsoft flows.

## Files

| File                                  | Purpose                                                                    |
| ------------------------------------- | -------------------------------------------------------------------------- |
| `hx-email-azure-app-cli.user.js`      | Tampermonkey script: floating panel on Azure portal + localhost Token Tool |
| `hx-email-gmail-app-password.user.js` | Gmail 应用专用密码助手：两步验证 / 生成 16 位密码 / IMAP 开关一键流程      |
| `KEYS.md`                             | Copy-ready Client ID / redirect / scope for HX-Email                       |
| `azure-app.json`                      | Machine-readable app summary                                               |
| `compat-check.mjs`                    | Local check that baked-in values match HX-Email defaults                   |

## Gmail 应用专用密码助手（hx-email-gmail-app-password.user.js）

前提：浏览器已登录 Google 账号。安装后访问以下任一页面，右下角会出现
「HX-Email Gmail 助手」浮动面板：

- `https://myaccount.google.com/apppasswords`（推荐入口）
- `https://myaccount.google.com/signinoptions/two-step-verification`
- `https://mail.google.com/mail/u/0/#settings/fwdandpop`

面板操作：

1. **① 两步验证**：未开启时自动点击「开始设置」，其余验证步骤（密码/手机）需本人完成；
2. **② 生成应用密码**：自动填名称（默认 `HX-Email`）→ 点「生成」→ 复制 `邮箱----密码`；
3. **③ IMAP**：Gmail 设置页中 IMAP 关闭时自动勾选「启用 IMAP」并保存。

面板内可修改应用名称与 HX-Email 地址。生成后打开 HX-Email → 账号 → 添加邮箱 →
Google Gmail → 应用专用密码（IMAP）→ Ctrl/Cmd+V 粘贴导入行即可。

URL 带 `?hx=auto` 时自动执行对应页面的主操作（油猴面板按钮始终可用）。
Chrome 扩展版（功能一致，含工具栏弹窗）见
[`extension/gmail-app-password/`](../extension/gmail-app-password/README.md)。

## Azure 应用注册助手（hx-email-azure-app-cli.user.js）

The Tampermonkey script below helps configuring / reusing the Azure App
Registration that HX-Email Token Tool needs for Outlook personal accounts.

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
