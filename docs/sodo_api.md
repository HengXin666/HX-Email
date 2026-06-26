# 邮箱服务器通信 API 分类汇总

> 来源: `server/` (HX-Email 主体) + `ref/outlookEmailPlus/` (参考项目)
> 范围: 仅涉及与邮箱服务器直接/间接通信的 API (IMAP/SMTP/Graph API/OAuth/代理)

---

## 目录
1. [IMAP 邮件获取](#1-imap-邮件获取)
2. [IMAP 邮件详情](#2-imap-邮件详情)
3. [IMAP 邮件删除](#3-imap-邮件删除)
4. [验证码/链接提取](#4-验证码链接提取)
5. [IMAP 消息持久化与同步](#5-imap-消息持久化与同步)
6. [IMAP 邮箱账号管理](#6-imap-邮箱账号管理)
7. [OAuth2 Token 刷新 (IMAP/Graph)](#7-oauth2-token-刷新-imapgraph)
8. [SMTP 外发测试](#8-smtp-外发测试)
9. [邮箱池管理](#9-邮箱池管理)
10. [代理连通性测试](#10-代理连通性测试)
11. [OAuth2 Token 工具 (PKCE)](#11-oauth2-token-工具-pkce)
12. [邮箱提供商信息](#12-邮箱提供商信息)
13. [外部 API (密钥认证)](#13-外部-api-密钥认证)
14. [Graph API —— Outlook Email Plus 特有](#14-graph-api--outlook-email-plus-特有)
15. [临时邮箱](#15-临时邮箱)

---

## 1. IMAP 邮件获取

从 IMAP 服务器拉取收件箱邮件列表。核心协议: **IMAP over SSL (993)**，认证方式: XOAUTH2 (Outlook) / LOGIN (其他)。

### HX-Email (`server/`)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/emails/{email_addr}` | 获取某邮箱的收件箱邮件列表，支持分页与文件夹筛选 |
| POST | `/api/v1/emails/batch` | 批量获取多个 IMAP 账号的邮件 |

**实现链路:**
- `api/impl/mail/email/routes.py` → `server/mail/impl/email_service.py`
- → `server/mail/imap/imap_provider.py::IMAPMailboxProvider.read_messages()`
- → `_imap_fetch()` 连接 IMAP 服务器 (SSL/TLS, OAuth 或密码认证)
- → `imap_helpers.py` 处理 OAuth token 缓存、代理连接、MIME 解析

**关键参数:** `folder` (默认 INBOX), `skip`, `top`, `method` (默认 imap)

### Outlook Email Plus (`ref/outlookEmailPlus/`)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/emails/{email_addr}` | 获取邮件列表 (先 Graph API，失败后回退到 IMAP 新旧服务器) |
| POST | `/api/emails/batch` | 批量获取多账号邮件 (支持测试模式/生产模式) |

**实现链路:**
- `routes/emails.py` → `services/imap.py` (Outlook XOAUTH2 IMAP)
- 或 → `services/imap_generic.py` (通用 IMAP LOGIN)
- 或 → `services/graph.py` (Microsoft Graph REST API, 仅 Outlook)

**特有功能:**
- 三重回退策略: Graph API → `outlook.live.com:993` → `outlook.office365.com:993`
- 并发连接多服务器取最先成功结果 (`get_emails_imap_concurrent`)
- 通用 IMAP 支持 ID 命令 (网易等要求)

---

## 2. IMAP 邮件详情

获取单封邮件的完整内容 (主题、发件人、正文、时间)。

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/email/{email_addr}/{message_id}` | 获取单封邮件完整详情 |

### Outlook Email Plus

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/email/{email_addr}/{message_id}` | 获取邮件详情 (Graph 优先, IMAP 回退) |

**实现差异:**
- HX-Email: 纯 IMAP FETCH 指定 UID
- Outlook Email Plus: Graph API `GET /me/messages/{id}` → IMAP 回退

---

## 3. IMAP 邮件删除

通过 IMAP 或 Graph API 删除指定邮件。

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/emails/delete` | 批量删除邮件 (当前为 stub，未实现 IMAP STORE +EXPUNGE) |

### Outlook Email Plus

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/emails/delete` | 批量删除 (Graph API POST /$batch → IMAP 新旧服务器回退) |

**实现文件:** `services/email_delete.py::delete_emails_with_fallback()`

---

## 4. 验证码/链接提取

从收件箱最新邮件中提取验证码 (默认6位数字) 或验证链接。核心链路: IMAP FETCH 最新 N 封 → 正则匹配 → 返回码/链接。

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/emails/{email_addr}/extract-verification` | 对某邮箱收件箱提取验证码/链接 |
| POST | `/api/v1/usable-emails/{id}/verification/read` | 扫描可用邮箱邮件中的验证码 (IMAP + 缓存优先) |
| GET | `/api/v1/usable-emails/{id}/verification/history` | 获取验证码提取历史记录 |
| GET | `/api/v1/usable-emails/{id}/verification/state` | 获取验证码扫描状态 |
| POST | `/api/v1/usable-emails/{id}/fetch-emails` | 触发 IMAP 抓取 → 持久化 → 提取验证码 (完整流水线) |

**实现链路:**
- `api/impl/mail/email/routes.py` → `server/mail/impl/email_service.py`
- → `server/mail/impl/email_fetch_service.py::fetch_and_store_for_account()` (后台线程 120s)
- → `server/mail/verification.py` 提取验证码/链接

### Outlook Email Plus

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/emails/{email_addr}/extract-verification` | 提取验证码 (查询 INBOX + JunkEmail 文件夹) |

**实现文件:** `services/verification_extractor.py`

---

## 5. IMAP 消息持久化与同步

IMAP 抓取后将邮件存入 SQLite `fetched_messages` 表，支持后续本地查询和验证码提取。

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/usable-emails/{id}/messages` | 列出已持久化的邮件 (本地 SQLite) |
| (后台服务) | — | `start_background_fetch()` 每 120s 自动遍历所有活跃账号拉取 IMAP |

**实现文件:**
- `server/mail/imap/message_store.py` — 消息去重 (SHA256 前32字符) + CRUD
- `server/mail/impl/email_fetch_service.py` — 后台 fetch 调度

---

## 6. IMAP 邮箱账号管理

管理用于 IMAP 连接的邮箱账号 (IMAP 凭证 / OAuth 凭据)。

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/email-accounts` | 创建邮箱账号 (IMAP host/port/密码 或 OAuth client_id/refresh_token) |
| GET | `/api/v1/email-accounts` | 列出所有邮箱账号 (分页/筛选/排序) |
| GET | `/api/v1/email-accounts/{id}` | 获取单个账号详情 |
| PUT | `/api/v1/email-accounts/{id}` | 更新账号 (IMAP 凭证/OAuth 凭证等) |
| DELETE | `/api/v1/email-accounts/{id}` | 删除账号 (级联删除关联数据) |
| POST | `/api/v1/email-accounts/{id}/deactivate` | 停用账号 |
| PATCH | `/api/v1/email-accounts/{id}/remark` | 更新备注 |
| DELETE | `/api/v1/email-accounts/email/{email_addr}` | 按邮箱地址删除账号 |
| GET | `/api/v1/email-accounts/search` | 全文搜索账号 |
| POST | `/api/v1/email-accounts/{id}/aliases` | 添加邮箱别名 |
| POST | `/api/v1/email-accounts/import` | 批量导入账号 (支持自动检测提供商 IMAP 配置) |
| POST | `/api/v1/email-accounts/import-preview` | 预览导入行数 |
| GET | `/api/v1/email-accounts/export-text` | 导出所有账号为文本格式 |
| GET | `/api/v1/email-accounts/export` | 导出所有账号 (含密码验证) |
| POST | `/api/v1/email-accounts/export-selected` | 导出指定分组账号 |
| POST | `/api/v1/export/verify` | 验证导出密码 |

### Outlook Email Plus

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/accounts` | 列出账号 (分页/搜索/过滤) |
| POST | `/api/accounts` | 添加/导入账号 (支持批量) |
| GET | `/api/accounts/{id}` | 获取账号详情 |
| PUT | `/api/accounts/{id}` | 更新账号 |
| DELETE | `/api/accounts/{id}` | 删除账号 |
| PATCH | `/api/accounts/{id}/remark` | 更新备注 |
| DELETE | `/api/accounts/email/{email_addr}` | 按邮箱删除 |
| GET | `/api/accounts/search` | 全局搜索 |
| POST | `/api/accounts/batch-update-group` | 批量移动分组 |
| POST | `/api/accounts/batch-delete` | 批量删除 |
| POST | `/api/accounts/batch-update-status` | 批量更新状态 |
| POST | `/api/accounts/tags` | 批量管理标签 |
| GET | `/api/accounts/export` | 导出所有账号 |
| POST | `/api/accounts/export-selected` | 导出选中账号 |
| POST | `/api/export/verify` | 验证导出密码 |

---

## 7. OAuth2 Token 刷新 (IMAP/Graph)

刷新 Microsoft OAuth2 refresh token，获取新的 access token 用于 IMAP XOAUTH2 或 Graph API。

**Token 端点:** `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`
**IMAP Scope:** `https://outlook.office.com/IMAP.AccessAsUser.All offline_access`
**Graph Scope:** `https://graph.microsoft.com/Mail.Read offline_access`

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/email-accounts/{id}/refresh` | 刷新单个账号 OAuth token |
| GET | `/api/v1/email-accounts/refresh-all` | SSE: 刷新所有活跃账号 |
| POST | `/api/v1/email-accounts/{id}/retry-refresh` | 重试刷新失败的账号 |
| POST | `/api/v1/email-accounts/refresh-failed` | SSE: 批量刷新所有上次失败的账号 |
| GET | `/api/v1/email-accounts/trigger-scheduled-refresh` | SSE: 手动触发定时刷新 |
| POST | `/api/v1/email-accounts/refresh/selected` | SSE: 刷新指定账号列表 |
| GET | `/api/v1/email-accounts/refresh-logs` | 获取刷新日志列表 |
| GET | `/api/v1/email-accounts/{id}/refresh-logs` | 获取单个账号刷新日志 |
| GET | `/api/v1/email-accounts/refresh-logs/failed` | 获取失败日志 |
| GET | `/api/v1/email-accounts/invalid-token-candidates` | 获取可能 token 失效的账号 |
| GET | `/api/v1/email-accounts/refresh-stats` | 刷新统计 |

**实现文件:**
- `server/mail/impl/refresh_service.py` — 刷新调度 + SSE 流
- `server/mail/imap/imap_helpers.py` — `get_imap_token()` / `try_get_imap_token()` 多租户尝试
- `server/mail/impl/oauth_tool.py` — `try_refresh_oauth_token()`

### Outlook Email Plus

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/accounts/{id}/refresh` | 刷新单个账号 OAuth token (含 token rotation) |
| GET | `/api/accounts/refresh-all` | 刷新所有账号 (SSE) |
| POST | `/api/accounts/{id}/retry-refresh` | 重试刷新 |
| POST | `/api/accounts/refresh-failed` | 重试所有失败账号 |
| GET | `/api/accounts/trigger-scheduled-refresh` | 手动触发定时刷新 |
| POST | `/api/accounts/refresh/selected` | 刷新指定账号列表 (SSE) |

**实现文件:**
- `services/refresh.py` — 刷新逻辑 + 失败分类
- `services/graph.py::test_refresh_token_with_rotation()` — Token 滚动更新

---

## 8. SMTP 外发测试

通过 SMTP 发送测试邮件 (用于验证通知配置)。

**协议:** SMTP_SSL (465) / STARTTLS (587)

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/settings/email-test` | 发送测试邮件通知 |

**实现文件:** `api/impl/settings/settings_test_routes.py` (使用 `smtplib`)

### Outlook Email Plus

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/settings/email-test` | 发送测试邮件通知 |

**实现文件:** `services/email_push.py` (SMTP 配置来自环境变量)

---

## 9. 邮箱池管理

管理可用的邮箱地址池，支持领取/释放/完成。底层依赖 IMAP 验证码提取链路。

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/mail-pool/entries` | 添加邮箱到池 |
| GET | `/api/v1/mail-pool/entries` | 列出池中邮箱 |
| POST | `/api/v1/mail-pool/claim` | 从池中领取随机邮箱 |
| POST | `/api/v1/mail-pool/entries/{id}/release` | 释放领取的邮箱 |
| POST | `/api/v1/mail-pool/entries/{id}/complete` | 标记任务完成 |
| POST | `/api/v1/mail-pool/entries/{id}/cooldown` | 冷却池条目 |
| GET | `/api/v1/pool-admin/accounts` | 管理员: 列出池账号 |
| POST | `/api/v1/pool-admin/accounts/{id}/action` | 管理员: 执行池操作 |

**实现文件:**
- `api/impl/mail/pool/pool_routes.py` + `pool_admin_routes.py`
- `server/mail/mail_pool.py`

### Outlook Email Plus

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/external/pool/claim-random` | 领取随机池邮箱 |
| POST | `/api/external/pool/claim-release` | 释放领取 |
| POST | `/api/external/pool/claim-complete` | 标记完成 |
| GET | `/api/external/pool/stats` | 池统计 |

**实现文件:** `routes/external_pool.py`, `services/pool.py`

---

## 10. 代理连通性测试

通过 SOCKS/HTTP 代理测试到 IMAP 服务器的连通性。

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/groups/proxy-test` | 测试代理到 `outlook.office365.com:993` 的 HTTP CONNECT 隧道 |

**实现文件:** `api/impl/workspace_routes.py` → `server/mail/imap/imap_helpers.py::imap_connect_via_proxy()`

**代理逻辑:** `load_group_proxy()` 从分组查询配置的代理 URL → `imap_connect_via_proxy()` 建立 HTTP CONNECT 隧道

---

## 11. OAuth2 Token 工具 (PKCE)

开发者工具: 执行 Microsoft OAuth2 PKCE 授权码流程，获取 refresh token 并保存到邮箱账号。

**协议:** OAuth 2.0 PKCE (S256)
**端点:** `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize` + `/token`

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/token-tool/config` | 获取 OAuth 工具配置 |
| POST | `/api/v1/token-tool/config` | 保存 OAuth 工具配置 |
| GET | `/api/v1/token-tool/accounts` | 列出可刷新 token 的 Outlook 账号 |
| POST | `/api/v1/token-tool/prepare` | 生成 PKCE 授权 URL |
| GET | `/api/v1/token-tool/callback` | OAuth 回调处理 (HTML 页面) |
| POST | `/api/v1/token-tool/exchange` | 用授权码换取 token |
| POST | `/api/v1/token-tool/save` | 保存 OAuth 凭据到账号 |

**实现文件:** `server/mail/impl/oauth_tool.py`

### Outlook Email Plus

| 方法 | 路径 | 描述 |
|------|------|------|
| GET/POST | `/token-tool` | Token 工具页面 |
| GET/POST | `/api/token-tool/*` | 同上 OAuth 流程 |

**实现文件:** `services/oauth_tool.py`

---

## 12. 邮箱提供商信息

返回支持的邮箱提供商及其 IMAP/SMTP 服务器配置。

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/providers` | 获取支持的邮箱提供商列表 |

**提供商配置:** `api/impl/mail/email/providers.py::SUPPORTED_PROVIDERS`

| 提供商 | IMAP Host | IMAP Port | SMTP Host | SMTP Port | 认证方式 |
|--------|-----------|-----------|-----------|-----------|----------|
| Outlook/Hotmail | outlook.office365.com | 993 | smtp-mail.outlook.com | 587 | oauth |
| Gmail | imap.gmail.com | 993 | smtp.gmail.com | 587 | oauth |
| QQ Mail | imap.qq.com | 993 | smtp.qq.com | 587 | password |
| 163 | imap.163.com | 993 | smtp.163.com | 465 | password |
| 126 | imap.126.com | 993 | smtp.126.com | 465 | password |
| Yahoo | imap.mail.yahoo.com | 993 | smtp.mail.yahoo.com | 587 | oauth |
| Custom | user-defined | 993 | user-defined | 587 | custom |

### Outlook Email Plus

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/providers` | 获取邮箱提供商列表 |

**实现文件:** `services/providers.py::MAIL_PROVIDERS` (额外包含 `aliyun`)

---

## 13. 外部 API (密钥认证)

使用 `X-API-Key` 头部认证的外部 API 路由，供浏览器扩展或第三方调用。所有邮件相关端点底层依赖 IMAP/Graph 读取。

### HX-Email

| 方法 | 路径 | 描述 | 底层协议 |
|------|------|------|----------|
| GET | `/api/external/messages` | 列出消息 (筛选/分页) | IMAP |
| GET | `/api/external/messages/latest` | 获取最新消息 | IMAP |
| GET | `/api/external/messages/{id}` | 获取消息详情 | IMAP |
| GET | `/api/external/messages/{id}/raw` | 获取原始 MIME 内容 | IMAP |
| GET | `/api/external/verification-code` | 提取验证码 | IMAP + 正则 |
| GET | `/api/external/verification-link` | 提取验证链接 | IMAP + 正则 |
| GET | `/api/external/wait-message` | 等待新消息 (同步/异步轮询) | IMAP 轮询 |
| GET | `/api/external/probe/{probe_id}` | 查询异步等待状态 | 内存存储 |
| POST | `/api/external/pool/claim-random` | 领取随机邮箱 | 池逻辑 |
| POST | `/api/external/pool/claim-release` | 释放领取 | 池逻辑 |
| POST | `/api/external/pool/claim-complete` | 标记完成 | 池逻辑 |
| GET | `/api/external/pool/stats` | 池统计 | 池逻辑 |

**实现文件:**
- `api/impl/external/message_routes.py` → `server/external_api/impl/mail/mail_service.py`
- `api/impl/external/pool_routes.py` → `server/external_api/impl/pool_service.py`

### Outlook Email Plus

| 方法 | 路径 | 描述 | 底层协议 |
|------|------|------|----------|
| GET | `/api/external/messages` | 列出消息 | Graph/IMAP |
| GET | `/api/external/messages/latest` | 最新消息 | Graph/IMAP |
| GET | `/api/external/messages/{id}` | 消息详情 | Graph/IMAP |
| GET | `/api/external/messages/{id}/raw` | 原始 MIME | Graph/IMAP |
| GET | `/api/external/verification-code` | 提取验证码 | Graph/IMAP |
| GET | `/api/external/verification-link` | 提取验证链接 | Graph/IMAP |
| GET | `/api/external/wait-message` | 等待新消息 | Graph/IMAP 轮询 |
| GET | `/api/external/probe/{probe_id}` | 异步探测状态 | 内存 |
| GET | `/api/external/account-status` | 账号状态 | — |
| GET | `/api/external/capabilities` | 外部 API 能力列表 | — |
| GET | `/api/external/health` | 外部 API 健康检查 | — |
| POST | `/api/external/pool/claim-random` | 领取池邮箱 | 池逻辑 |
| POST | `/api/external/pool/claim-release` | 释放 | 池逻辑 |
| POST | `/api/external/pool/claim-complete` | 完成 | 池逻辑 |
| GET | `/api/external/pool/stats` | 统计 | 池逻辑 |

---

## 14. Graph API —— Outlook Email Plus 特有

> HX-Email `server/` 无 Graph API 实现，仅 `ref/outlookEmailPlus/` 包含。

Microsoft Graph REST API 用于访问 Outlook/Hotmail 邮箱。这是 IMAP 的高层替代方案。

**实现文件:** `services/graph.py`

**使用的 Microsoft Graph 端点:**

| 操作 | Graph API 端点 |
|------|----------------|
| 获取 OAuth token | `POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token` |
| 列出消息 | `GET /v1.0/me/mailFolders/{folder}/messages?$top=N&$skip=M&$orderby=receivedDateTime desc` |
| 获取消息详情 | `GET /v1.0/me/messages/{id}` |
| 获取 MIME 原始内容 | `GET /v1.0/me/messages/{id}/$value` |
| 批量删除 | `POST /v1.0/$batch` |

**核心函数:**
- `get_emails_graph()` — 获取邮件列表
- `get_email_detail_graph()` — 获取邮件详情
- `get_email_raw_graph()` — 获取原始 MIME
- `delete_emails_graph()` — 批量删除
- `test_refresh_token_with_rotation()` — Token 测试 + 滚动更新
- `get_access_token_graph()` — 获取 access token

**回退策略:** Graph API → IMAP (`outlook.live.com`) → IMAP (`outlook.office365.com`)

**适用范围:** 仅 Outlook/Hotmail 类型账号 (provider == "outlook")

---

## 15. 临时邮箱

不依赖真实 IMAP 服务器，而是通过上游临时邮箱提供商 API 创建一次性邮箱。

### HX-Email

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/temp-emails` | 列出临时邮箱 |
| POST | `/api/v1/temp-emails/generate` | 生成新的临时邮箱 |
| GET | `/api/v1/temp-emails/{addr}/messages` | 获取临时邮箱消息 |
| GET | `/api/v1/temp-emails/{addr}/messages/{id}` | 获取临时消息详情 |
| DELETE | `/api/v1/temp-emails/{addr}` | 删除临时邮箱 |
| POST | `/api/v1/temp-emails/{addr}/refresh` | 刷新临时邮箱消息 |

### Outlook Email Plus

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/temp-emails` | 列出 |
| GET | `/api/temp-emails/options` | 获取生成选项 |
| POST | `/api/temp-emails/generate` | 生成 |
| POST | `/api/external/temp-emails/apply` | 外部 API: 申请临时邮箱 |
| POST | `/api/external/temp-emails/{token}/finish` | 外部 API: 完成临时邮箱 |

**实现文件:**
- HX-Email: `server/mail/temp_mail.py` + `server/mail/impl/temp_mail/`
- Outlook Email Plus: `services/temp_mail_provider_factory.py` + `services/temp_mail_provider_cf.py`

---

## 协议总览

| 协议 | HX-Email | Outlook Email Plus | 用途 |
|------|----------|-------------------|------|
| **IMAP SSL (993)** | ✅ `imap_provider.py` + `imap_helpers.py` | ✅ `imap.py` + `imap_generic.py` | 邮件获取/详情/删除 |
| **IMAP XOAUTH2** | ✅ (Outlook) | ✅ (Outlook) | Outlook OAuth 2.0 IMAP 认证 |
| **IMAP LOGIN** | ✅ (密码/应用密码) | ✅ (Gmail/QQ/163/126) | 标准 IMAP 密码认证 |
| **Microsoft Graph REST** | ❌ | ✅ `graph.py` | Outlook 高层 REST API (备选+首选) |
| **SMTP SSL (465)** | ✅ `smtplib` | ✅ `email_push.py` | 外发测试邮件 |
| **SMTP STARTTLS (587)** | ✅ `smtplib` | ✅ `email_push.py` | 外发测试邮件 |
| **OAuth 2.0 PKCE** | ✅ `oauth_tool.py` | ✅ `oauth_tool.py` | 授权码流程获取 refresh token |
| **OAuth 2.0 Token Refresh** | ✅ `refresh_service.py` | ✅ `refresh.py` | 刷新 access token |
| **HTTP CONNECT Proxy** | ✅ `imap_connect_via_proxy()` | ❌ | 通过代理连接 IMAP 服务器 |
| **临时邮箱 API** | ✅ CF Worker / 上游 API | ✅ 插件化上游提供商 | 一次性邮箱生成与消息轮询 |
| **轮询等待** | ✅ `wait_service.py` | ✅ `external_api.py` | 阻塞/异步等待新邮件到达 |

---

## 关键文件索引

### HX-Email (`server/`)

| 文件 | 职责 |
|------|------|
| `src/hx_email/app.py` | FastAPI 工厂, 创建 IMAPMailboxProvider, 启后台 fetch |
| `src/hx_email/server/mail/imap/imap_provider.py` | IMAP 连接核心 (SSL/TLS, XOAUTH2, LOGIN, FETCH) |
| `src/hx_email/server/mail/imap/imap_helpers.py` | OAuth token 缓存, MIME 解析, 代理连接, Outlook 多服务器回退 |
| `src/hx_email/server/mail/imap/message_store.py` | SQLite 消息持久化 |
| `src/hx_email/server/mail/impl/email_fetch_service.py` | 后台 fetch 调度 (120s 间隔) |
| `src/hx_email/server/mail/impl/email_service.py` | 高层邮件操作 (fetch/list/detail/delete/batch) |
| `src/hx_email/server/mail/impl/refresh_service.py` | OAuth token 刷新 + SSE 流 |
| `src/hx_email/server/mail/impl/oauth_tool.py` | OAuth2 PKCE 流程 |
| `src/hx_email/server/mail/verification.py` | 验证码提取, MailboxProvider 协议 |
| `src/hx_email/api/impl/mail/email/routes.py` | 邮件 API 路由 |
| `src/hx_email/api/impl/mail/email/providers.py` | 提供商 IMAP/SMTP 配置 |
| `src/hx_email/api/impl/mail/usable_email_routes.py` | 可用邮箱路由 |
| `src/hx_email/api/impl/mail/account_routes.py` | 邮箱账号 CRUD 路由 |
| `src/hx_email/api/impl/mail/account_transfer_routes.py` | 账号导入/导出路由 |
| `src/hx_email/api/impl/mail/token_tool_routes.py` | OAuth Token 工具路由 |
| `src/hx_email/api/impl/mail/actions/batch_routes.py` | 批量操作路由 |
| `src/hx_email/api/impl/mail/actions/export_routes.py` | 导出验证路由 |
| `src/hx_email/api/impl/mail/pool/pool_routes.py` | 邮箱池路由 |
| `src/hx_email/api/impl/mail/pool/pool_admin_routes.py` | 池管理路由 |
| `src/hx_email/api/impl/mail/refresh/refresh_routes.py` | Token 刷新 SSE 路由 |
| `src/hx_email/api/impl/mail/refresh/refresh_log_routes.py` | 刷新日志路由 |
| `src/hx_email/api/impl/workspace_routes.py` | 代理测试路由 |
| `src/hx_email/api/impl/settings/settings_test_routes.py` | SMTP 测试路由 |
| `src/hx_email/api/impl/external/` | 外部 API 路由 (消息/池/系统/临时邮箱) |
| `src/hx_email/server/external_api/impl/mail/mail_service.py` | 外部 API 邮件操作 |
| `src/hx_email/server/external_api/impl/mail/wait_service.py` | 等待新邮件服务 |

### Outlook Email Plus (`ref/outlookEmailPlus/`)

| 文件 | 职责 |
|------|------|
| `outlook_web/services/imap.py` | Outlook XOAUTH2 IMAP 读取 |
| `outlook_web/services/imap_generic.py` | 通用 IMAP LOGIN 读取 |
| `outlook_web/services/graph.py` | Microsoft Graph REST API |
| `outlook_web/services/email_delete.py` | 邮件删除 (Graph + IMAP 回退) |
| `outlook_web/services/email_push.py` | SMTP 外发通知 |
| `outlook_web/services/refresh.py` | OAuth token 刷新 + SSE |
| `outlook_web/services/oauth_tool.py` | OAuth2 PKCE 流程 |
| `outlook_web/services/providers.py` | 邮箱提供商配置 |
| `outlook_web/services/verification_extractor.py` | 验证码提取 |
| `outlook_web/services/pool.py` | 邮箱池逻辑 |
| `outlook_web/routes/emails.py` | 邮件相关路由 |
| `outlook_web/routes/accounts.py` | 账号管理路由 |
| `outlook_web/routes/external_pool.py` | 外部池路由 |
| `outlook_web/routes/external_temp_emails.py` | 外部临时邮箱路由 |
| `outlook_web/routes/settings.py` | 设置 + SMTP 测试路由 |
| `outlook_web/controllers/emails.py` | 邮件控制器 |
| `outlook_web/controllers/accounts.py` | 账号控制器 |
