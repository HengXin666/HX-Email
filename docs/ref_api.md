# API 参考文档

> 基于 `ref/outlookEmailPlus` 项目逆向梳理，按前端页面划分 API，
> 非前端页面使用的 API（对外接口、系统探活等）单独归类。

---

## 约定

- **认证**: `Session` = 登录会话 Cookie; `API-Key` = 请求头 `X-API-Key`
- **内部响应格式**:
  ```json
  {"success": true, ...}
  {"success": false, "error": {"code": "...", "message": "...", "type": "...", "status": 400}}
  ```
- **外部响应格式**:
  ```json
  {"success": true, "code": "OK", "message": "success", "data": {...}}
  {"success": false, "code": "ERROR_CODE", "message": "...", "data": null}
  ```
- **SSE**: `text/event-stream` 流式响应

---

## 1. 登录页

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/login` | 无 | — | HTML 页面 | 登录页面 |
| POST | `/login` | 无 | `password` (form) | 重定向到 `/` 或返回登录页 | 密码验证登录 |
| GET | `/logout` | 无 | — | 重定向到 `/login` | 清除会话并登出 |
| GET | `/favicon.ico` | 无 | — | ico 文件 | 网站图标 |

---

## 2. 数据概览（Dashboard）

> 侧边栏: 数据概览, 路由值: `dashboard`

### 2.1 概览统计

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/overview/summary` | Session | — | `{"success": true, "total_accounts": int, "active_accounts": int, ...}` | 总览统计（30s TTL 缓存） |
| GET | `/api/overview/verification` | Session | — | `{"success": true, ...}` | 验证码提取统计 |
| GET | `/api/overview/verification-stats` | Session | — | 同上（别名） | 验证码提取统计 |
| GET | `/api/overview/external-api` | Session | — | `{"success": true, ...}` | 对外 API 调用统计 |
| GET | `/api/overview/external-api-stats` | Session | — | 同上（别名） | 对外 API 调用统计 |
| GET | `/api/overview/pool` | Session | — | `{"success": true, ...}` | 邮箱池状态统计 |
| GET | `/api/overview/pool-stats` | Session | — | 同上（别名） | 邮箱池状态统计 |
| GET | `/api/overview/activity` | Session | — | `{"success": true, ...}` | 系统活动统计 |

### 2.2 Dashboard 额外引用的 API

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/accounts/refresh-logs/failed` | Session | — | `{"success": true, "logs": [...]}` | 近期失败的刷新日志 |
| GET | `/api/accounts/refresh-stats` | Session | — | `{"success": true, ...}` | 刷新统计摘要 |
| GET | `/api/accounts/invalid-token-candidates` | Session | `?limit=&offset=` | `{"success": true, "candidates": [...]}` | 疑似 Token 失效的账号列表 |

---

## 3. 账号管理（Mailbox）

> 侧边栏: 账号管理, 路由值: `mailbox`
> 包含分组管理、标签管理、邮件查看、批量操作、导出

### 3.1 首屏引导

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/bootstrap` | Session | — | `{"success": true, "bootstrap": {"ui_layout_v2": {...}, "enable_auto_polling": bool, "polling_interval": int, ...}}` | 首屏初始化数据（布局+轮询配置） |

### 3.2 分组 (Groups)

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/groups` | Session | — | `{"success": true, "groups": [{"id": int, "name": str, "color": str, "description": str, "is_system": bool, "account_count": int, ...}]}` | 获取所有分组 |
| GET | `/api/groups/:id` | Session | `id` (路径) | `{"success": true, "group": {...}}` | 获取单个分组详情 |
| POST | `/api/groups` | Session | JSON `{"name": str, "description?": str, "color?": str, "proxy_url?": str, "verification_code_length?": int, "verification_code_regex?": str}` | `{"success": true, "group_id": int}` | 创建新分组 |
| PUT | `/api/groups/:id` | Session | JSON（同 POST 字段，均为可选） | `{"success": true}` | 更新分组 |
| DELETE | `/api/groups/:id` | Session | `id` (路径) | `{"success": true}` | 删除分组 |
| GET | `/api/groups/:id/export` | Session | `X-Export-Token` 请求头 | 文本文件下载 (.txt) | 导出分组内所有账号 |

### 3.3 标签 (Tags)

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/tags` | Session | — | `{"success": true, "tags": [{"id": int, "name": str, "color": str}]}` | 获取所有标签 |
| POST | `/api/tags` | Session | JSON `{"name": str, "color?": str}` | `{"success": true, "tag": {"id": int, "name": str, "color": str}}` | 创建标签 |
| DELETE | `/api/tags/:tag_id` | Session | `tag_id` (路径) | `{"success": true}` | 删除标签 |

### 3.4 账号 CRUD

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/accounts` | Session | `?group_id=&page=&page_size=&search=&sort_by=&sort_order=&tag_id[]=&tag_ids=` | `{"success": true, "accounts": [...], "pagination": {"page": int, "page_size": int, "total_count": int, "total_pages": int}}` | 分页获取账号列表（按分组/搜索/标签筛选） |
| POST | `/api/accounts` | Session | JSON `{"account_string": str, "group_id": int, "provider?": str, "imap_host?": str, "imap_port?": int, "add_to_pool?": bool}` | `{"success": true, "account_id": int}` | 导入/添加账号 |
| GET | `/api/accounts/:account_id` | Session | `account_id` (路径) | `{"success": true, "account": {...}}` | 获取单个账号详情（敏感字段脱敏） |
| PUT | `/api/accounts/:account_id` | Session | JSON `{"email?": str, "password?": str, "client_id?": str, "refresh_token?": str, "group_id?": int, "remark?": str, "status?": str}` | `{"success": true}` | 更新账号信息 |
| DELETE | `/api/accounts/:account_id` | Session | `account_id` (路径) | `{"success": true}` | 删除单个账号 |
| PATCH | `/api/accounts/:account_id/remark` | Session | JSON `{"remark": str}` | `{"success": true}` | 更新账号备注 |
| DELETE | `/api/accounts/email/:email_addr` | Session | `email_addr` (路径) | `{"success": true}` | 按邮箱地址删除账号 |
| GET | `/api/accounts/search` | Session | `?q=` | `{"success": true, "accounts": [...]}` | 全库搜索账号 |

### 3.5 批量操作

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| POST | `/api/accounts/batch-update-group` | Session | JSON `{"account_ids": [int, ...], "group_id": int}` | `{"success": true}` | 批量移动账号到分组 |
| POST | `/api/accounts/batch-delete` | Session | JSON `{"account_ids": [int, ...]}` | `{"success": true}` | 批量删除账号 |
| POST | `/api/accounts/batch-update-status` | Session | JSON `{"account_ids": [int, ...], "status": str}` | `{"success": true}` | 批量更新账号状态 (active/inactive/disabled) |
| POST | `/api/accounts/batch-notification-toggle` | Session | JSON `{"account_ids": [int, ...], "enabled": bool}` | `{"success": true}` | 批量切换通知开关 |
| POST | `/api/accounts/tags` | Session | JSON `{"account_ids": [int, ...], "tag_id": int, "action": str}` | `{"success": true}` | 批量管理账号标签 (add/remove) |

### 3.6 导出

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/accounts/export` | Session | `X-Export-Token` 请求头 | 文本文件下载 (.txt) | 导出全部账号 |
| POST | `/api/accounts/export-selected` | Session | JSON `{"group_ids": [int, ...], "verify_token?": str}` + `X-Export-Token` 请求头 | 文本文件下载 (.txt) | 导出选中分组的账号 |
| POST | `/api/export/verify` | Session | JSON `{"password": str}` | `{"success": true, "verify_token": str}` | 二次密码验证，获取导出 Token |

### 3.7 Token 刷新

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| POST | `/api/accounts/:account_id/refresh` | Session | `account_id` (路径) | `{"success": true}` | 同步刷新单个账号 Token |
| GET | `/api/accounts/refresh-all` | Session | — | **SSE 流** | 刷新全部账号 Token（SSE 推送进度） |
| POST | `/api/accounts/:account_id/retry-refresh` | Session | `account_id` (路径) | `{"success": true}` | 重试刷新单个账号 Token |
| POST | `/api/accounts/refresh-failed` | Session | — | `{"success": true}` | 重试刷新所有失败的账号 |
| GET | `/api/accounts/trigger-scheduled-refresh` | Session | `?force=` | **SSE 流** | 触发定时刷新任务 |
| POST | `/api/accounts/refresh/selected` | Session | JSON `{"account_ids": [int, ...]}` | **SSE 流** | 刷新选中的多个账号 |

### 3.8 刷新日志

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/accounts/refresh-logs` | Session | `?limit=&offset=` | `{"success": true, "logs": [...], "total": int}` | 获取全局刷新日志 |
| GET | `/api/accounts/:account_id/refresh-logs` | Session | `?limit=&offset=` | `{"success": true, "logs": [...]}` | 获取单个账号刷新日志 |
| GET | `/api/accounts/refresh-logs/failed` | Session | — | `{"success": true, "logs": [...]}` | 获取近期失败的刷新日志 |
| GET | `/api/accounts/invalid-token-candidates` | Session | `?limit=&offset=` | `{"success": true, "candidates": [...]}` | 疑似 Token 失效的账号列表 |
| GET | `/api/accounts/refresh-stats` | Session | — | `{"success": true, ...}` | 刷新统计摘要 |

### 3.9 通知切换

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| POST | `/api/accounts/:account_id/telegram-toggle` | Session | JSON `{"enabled": bool}` | `{"success": true}` | 切换单个账号的 Telegram 通知 |

### 3.10 邮件

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| POST | `/api/emails/batch` | Session | JSON `{"account_ids": [int, ...], "folders?": [str, ...], "skip?": int, "top?": int}` | `{"success": true, "results": [...], "summary": {"total_accounts": int, "success_accounts": int, "failed_accounts": int}}` | 批量拉取多账号邮件 |
| GET | `/api/emails/:email_addr` | Session | `?folder=&skip=&top=&method=` | `{"success": true, "emails": [...], "method": str, "has_more": bool}` | 获取指定邮箱的邮件列表（自动回退 Graph→IMAP New→IMAP Old） |
| GET | `/api/emails/:email_addr/extract-verification` | Session | `?code_length=&code_regex=&code_source=` | `{"success": true, "verification_code": str, ...}` | 从最新邮件中提取验证码 |
| POST | `/api/emails/delete` | Session | JSON `{"email": str, "ids": [str, ...]}` | `{"success": true}` | 批量删除邮件（永久删除） |
| GET | `/api/email/:email_addr/:message_id` | Session | `?folder=&method=` | `{"success": true, "email": {"id": str, "subject": str, "from": str, "to": str, "date": str, "body": str, "body_type": str}}` | 获取单封邮件详情 |
| GET | `/api/providers` | Session | — | `{"success": true, "providers": [...]}` | 获取支持的邮箱提供商列表 |

---

## 4. 号池管理（Pool Admin）

> 侧边栏: 号池管理, 路由值: `pool-admin`

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/pool-admin/accounts` | Session | `?in_pool=&pool_status=&provider=&group_id=&search=&page=&page_size=` | `{"success": true, "accounts": [...], "pagination": {...}}` | 查询邮箱池中的账号列表 |
| POST | `/api/pool-admin/accounts/:account_id/action` | Session | JSON `{"action": str, ...}` | `{"success": true}` | 对池中账号执行操作 (claim/release/complete/freeze/cooldown/retire 等) |

> 号池管理页面也引用 `GET /api/groups` 获取分组筛选列表。

---

## 5. 临时邮箱（Temp Emails）

> 侧边栏: 临时邮箱, 路由值: `temp-emails`

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/temp-emails` | Session | — | `{"success": true, "emails": [...]}` | 获取所有临时邮箱 |
| GET | `/api/temp-emails/options` | Session | `?provider_name=` | `{"success": true, "options": {...}}` | 获取临时邮箱注册选项（域名/前缀规则等） |
| POST | `/api/temp-emails/generate` | Session | JSON `{"prefix?": str, "domain?": str, "provider_name?": str}` | `{"success": true, "email": str, ...}` | 生成新的临时邮箱 |
| GET | `/api/temp-emails/:email_addr/extract-verification` | Session | `email_addr` (路径) | `{"success": true, "verification_code": str, ...}` | 从临时邮箱提取验证码 |
| DELETE | `/api/temp-emails/:email_addr` | Session | `email_addr` (路径) | `{"success": true}` | 删除临时邮箱 |
| GET | `/api/temp-emails/:email_addr/messages` | Session | `?sync_remote=` | `{"success": true, "messages": [...]}` | 获取临时邮箱的邮件列表 |
| GET | `/api/temp-emails/:email_addr/messages/:message_id` | Session | `?refresh_if_missing=` | `{"success": true, "message": {...}}` | 获取单封临时邮件详情 |
| DELETE | `/api/temp-emails/:email_addr/messages/:message_id` | Session | 路径参数 | `{"success": true}` | 删除单封临时邮件 |
| DELETE | `/api/temp-emails/:email_addr/clear` | Session | `email_addr` (路径) | `{"success": true}` | 清空临时邮箱所有邮件 |
| POST | `/api/temp-emails/:email_addr/refresh` | Session | `email_addr` (路径) | `{"success": true}` | 手动刷新临时邮箱邮件 |

---

## 6. 刷新日志（Refresh Log）

> 侧边栏: 刷新日志, 路由值: `refresh-log`

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/accounts/refresh-logs` | Session | `?limit=200` | `{"success": true, "logs": [...], "total": int}` | 获取 Token 刷新历史日志 |

---

## 7. 系统设置（Settings）

> 侧边栏: 系统设置, 路由值: `settings`
> 子选项卡: 基础 / 临时邮箱 / API 安全 / 自动化

### 7.1 设置读写

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/settings` | Session | — | `{"success": true, ...}` (返回所有设置项的扁平 JSON) | 获取全部系统设置 |
| PUT | `/api/settings` | Session | JSON（包含任意可设置字段，详见下方） | `{"success": true}` | 更新系统设置 |

**PUT `/api/settings` 支持的字段（部分关键字段）**:
- `login_password` — 登录密码
- `verification_ai_enabled` / `verification_ai_base_url` / `verification_ai_model` / `verification_ai_api_key` — AI 验证码提取
- `temp_mail_provider` / `temp_mail_api_base_url` / `temp_mail_api_key` / `temp_mail_domains` / `temp_mail_default_domain` / `temp_mail_prefix_rules` — 临时邮箱
- `cf_worker_domains` / `cf_worker_default_domain` / `cf_worker_prefix_rules` / `cf_worker_base_url` / `cf_worker_admin_key` — Cloudflare Worker
- `external_api_key` / `external_api_keys` / `external_api_public_mode` / `external_api_ip_whitelist` / `external_api_rate_limit_per_minute` — 对外 API 安全
- `external_api_disable_raw_content` / `external_api_disable_wait_message` — 对外 API 功能开关
- `pool_external_enabled` — 外部邮箱池开关
- `enable_scheduled_refresh` / `refresh_interval_days` / `refresh_delay_seconds` / `refresh_cron` / `use_cron_schedule` — 定时刷新
- `enable_auto_polling` / `polling_interval` / `polling_count` — 自动轮询
- `enable_compact_auto_poll` / `compact_poll_interval` / `compact_poll_max_count` — 紧凑模式轮询
- `email_notification_enabled` / `email_notification_recipient` — 邮件通知
- `webhook_notification_enabled` / `webhook_notification_url` / `webhook_notification_token` — Webhook 通知
- `telegram_bot_token` / `telegram_chat_id` / `telegram_poll_interval` / `telegram_proxy_url` — Telegram 通知
- `watchtower_url` / `watchtower_token` / `update_method` — 一键更新
- `ui_layout_v2` — UI 布局配置

### 7.2 设置 - 测试与校验

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| POST | `/api/settings/validate-cron` | Session | JSON `{"cron_expression": str}` | `{"success": true, "valid": bool}` | 校验 Cron 表达式 |
| POST | `/api/settings/telegram-test` | Session | — (使用已保存配置) | `{"success": true}` | 测试 Telegram 通知 |
| POST | `/api/settings/test-telegram-proxy` | Session | JSON `{"proxy_url": str}` | `{"success": true}` | 测试 Telegram 代理连通性 |
| POST | `/api/settings/email-test` | Session | — (使用已保存配置) | `{"success": true}` | 测试邮件通知 |
| POST | `/api/settings/webhook-test` | Session | — (使用已保存配置) | `{"success": true}` | 测试 Webhook 通知 |
| POST | `/api/settings/verification-ai-test` | Session | JSON `{"subject?": str, "body?": str, "body_html?": str, "code_length?": int, "code_regex?": str}` | `{"success": true}` | 测试 AI 验证码提取 |
| POST | `/api/settings/cf-worker-sync-domains` | Session | — | `{"success": true}` | 从 CF Worker 同步域名列表 |
| GET | `/api/settings/external-api-key/plaintext` | Session | — | `{"success": true, "api_key": str}` | 获取 API Key 明文 |

### 7.3 系统维护（设置页引用）

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/system/version-check` | Session | — | `{"success": true, "current_version": str, "latest_version": str, "has_update": bool}` | 检查版本更新 |
| GET | `/api/system/deployment-info` | Session | — | `{"success": true, ...}` | 获取部署信息 |
| POST | `/api/system/trigger-update` | Session | — | `{"success": true}` | 触发 Docker 一键更新 |
| POST | `/api/system/test-watchtower` | Session | — | `{"success": true}` | 测试 Watchtower 连通性 |
| POST | `/api/system/reload-plugins` | Session | — | `{"success": true}` | 重新加载临时邮箱插件 |

---

## 8. 审计日志（Audit Log）

> 侧边栏: 审计日志, 路由值: `audit`

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/audit-logs` | Session | `?limit=&offset=&action=&resource_type=` | `{"success": true, "logs": [...], "total": int}` | 分页查询审计日志 |

---

## 9. Token 工具（Token Tool）

> 独立弹窗页面 (非 SPA 内页), 路由: `/token-tool`

### 9.1 页面渲染

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/token-tool` | Session | — | HTML 页面 | Token 工具页面 |
| GET | `/token-tool/callback` | 无 | OAuth 回调参数 (`?code=&state=`) | HTML 页面 (popup_result) | OAuth 回调处理页 |

### 9.2 Token 工具 API

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| POST | `/api/token-tool/prepare` | Session | JSON `{"client_id": str, "redirect_uri": str}` | `{"success": true, "auth_url": str, "state": str}` | 准备 OAuth 授权请求 |
| POST | `/api/token-tool/exchange` | Session | JSON `{"code": str, "state": str, "client_id": str, "redirect_uri": str}` | `{"success": true, "token_data": {...}}` | 用授权码兑换 Token |
| POST | `/api/token-tool/save` | Session | JSON `{"account_id": int, "client_id": str, "refresh_token": str}` | `{"success": true}` | 将 Token 保存到账号 |
| GET | `/api/token-tool/accounts` | Session | — | `{"success": true, "accounts": [...]}` | 获取账号列表（用于匹配） |
| GET | `/api/token-tool/config` | Session | — | `{"success": true, "config": {...}}` | 获取 OAuth 配置 |
| POST | `/api/token-tool/config` | Session | JSON `{"client_id": str, ...}` | `{"success": true}` | 保存 OAuth 配置 |

---

## 10. 全局 / 跨页面共享 API

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/api/csrf-token` | 无 | — | `{"csrf_token": str}` | 获取 CSRF Token |
| GET | `/api/scheduler/status` | Session | — | `{"success": true, "status": {...}}` | 获取调度器运行状态 |
| GET | `/api/system/health` | Session | — | `{"success": true, ...}` | 系统健康检查（内部） |
| GET | `/api/system/diagnostics` | Session | — | `{"success": true, ...}` | 系统诊断信息 |
| GET | `/api/system/upgrade-status` | Session | — | `{"success": true, ...}` | 数据库升级状态 |
| GET | `/api/plugins` | Session | — | `{"success": true, "plugins": [...]}` | 获取已安装插件列表 |
| POST | `/api/plugins/install` | Session | JSON `{"source": str, ...}` | `{"success": true}` | 安装临时邮箱插件 |
| POST | `/api/plugins/:name/uninstall` | Session | JSON `{}` | `{"success": true}` | 卸载插件 |
| GET | `/api/plugins/:name/config/schema` | Session | `name` (路径) | `{"success": true, "schema": {...}}` | 获取插件配置 Schema |
| GET | `/api/plugins/:name/config` | Session | `name` (路径) | `{"success": true, "config": {...}}` | 获取插件当前配置 |
| POST | `/api/plugins/:name/config` | Session | JSON `{...}` | `{"success": true}` | 保存插件配置 |
| POST | `/api/plugins/:name/test-connection` | Session | `name` (路径) | `{"success": true}` | 测试插件连接 |

---

## 11. 非前端 API（对外接口 / 外部调用）

> 此类接口不直接服务前端页面，面向第三方客户端/注册机调用。
> 认证方式: `X-API-Key` 请求头。
> 响应格式: `{"success": true, "code": "OK", "message": "success", "data": {...}}`

### 11.1 外部邮件接口

| 方法 | 端点 | 认证 | 请求参数 | 返回值 `data` 字段 | 描述 |
|------|------|------|----------|---------------------|------|
| GET | `/api/external/messages` | API-Key | `?email=&folder=&skip=&top=&from_contains=&subject_contains=&since_minutes=&claim_token=` | `{"emails": [...], "count": int, "has_more": bool}` | 获取邮件列表 |
| GET | `/api/external/messages/latest` | API-Key | 同上 | `{"id": str, "subject": str, "from": str, ...}` | 获取最新一封邮件 |
| GET | `/api/external/messages/:message_id` | API-Key | `?email=&folder=&claim_token=` | `{"id": str, "subject": str, "body": str, ...}` | 获取单封邮件详情 |
| GET | `/api/external/messages/:message_id/raw` | API-Key | `?email=&folder=&claim_token=` | `{"raw": str, ...}` | 获取邮件原始内容 |
| GET | `/api/external/verification-code` | API-Key | `?email=&folder=&from_contains=&subject_contains=&since_minutes=&code_length=&code_regex=&code_source=&claim_token=` | `{"verification_code": str, "matched_email_id": str, ...}` | 提取验证码 |
| GET | `/api/external/verification-link` | API-Key | `?email=&folder=&from_contains=&subject_contains=&since_minutes=&claim_token=` | `{"verification_link": str, "matched_email_id": str, ...}` | 提取验证链接 |
| GET | `/api/external/wait-message` | API-Key | `?email=&folder=&from_contains=&subject_contains=&since_minutes=&timeout_seconds=&poll_interval=&mode=&claim_token=` | `{"id": str, "subject": str, ...}` (sync) / `{"probe_id": str}` (async, 202) | 阻塞等待新邮件到达 |
| GET | `/api/external/probe/:probe_id` | API-Key | `probe_id` (路径) | `{"status": str, "result": {...} \| null}` | 查询异步探测状态 |

**通用查询参数说明**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `email` | string | — | 目标邮箱地址（必填） |
| `folder` | string | `inbox` | 邮件文件夹: `inbox` / `junkemail` / `deleteditems` |
| `skip` | int | 0 | 跳过邮件数 |
| `top` | int | 20 | 返回邮件数上限 (1-50) |
| `from_contains` | string | — | 按发件人过滤 |
| `subject_contains` | string | — | 按主题过滤 |
| `since_minutes` | int | — | 仅查最近 N 分钟内的邮件 |
| `claim_token` | string | — | 邮箱池领取凭证（自动推断 email） |
| `code_length` | int | — | 验证码长度 |
| `code_regex` | string | — | 验证码正则 |
| `code_source` | string | `all` | 验证码来源: `subject` / `content` / `html` / `all` |
| `timeout_seconds` | int | 30 | 等待超时秒数 |
| `poll_interval` | int | 5 | 轮询间隔秒数 |
| `mode` | string | `sync` | 等待模式: `sync` / `async` |

### 11.2 外部邮箱池接口

| 方法 | 端点 | 认证 | 请求参数 | 返回值 `data` 字段 | 描述 |
|------|------|------|----------|---------------------|------|
| POST | `/api/external/pool/claim-random` | API-Key | JSON `{"caller_id": str, "task_id": str, "provider?": str, "project_key?": str, "email_domain?": str}` | `{"account_id": int, "email": str, "claim_token": str, ...}` | 从池中随机领取一个邮箱 |
| POST | `/api/external/pool/claim-release` | API-Key | JSON `{"account_id": int, "claim_token": str, "caller_id": str, "task_id": str, "reason?": str}` | `{}` | 释放已领取的邮箱 |
| POST | `/api/external/pool/claim-complete` | API-Key | JSON `{"account_id": int, "claim_token": str, "caller_id": str, "task_id": str, "result": str, "detail?": str}` | `{}` | 完成任务并释放邮箱 |
| GET | `/api/external/pool/stats` | API-Key | — | `{"total": int, "available": int, "claimed": int, ...}` | 获取邮箱池统计信息 |

> 外部池接口需要满足: ① `pool_external_enabled` 为 true; ② API Key 拥有 `pool_access` 权限。

### 11.3 外部临时邮箱接口

| 方法 | 端点 | 认证 | 请求参数 | 返回值 `data` 字段 | 描述 |
|------|------|------|----------|---------------------|------|
| POST | `/api/external/temp-emails/apply` | API-Key | JSON `{"caller_id": str, "task_id": str, "prefix?": str, "domain?": str}` | `{"email": str, "prefix": str, "domain": str, "task_token": str, ...}` | 申请临时邮箱 |
| POST | `/api/external/temp-emails/:task_token/finish` | API-Key | JSON `{"result?": str, "detail?": str}` | `{}` | 完成任务并释放临时邮箱 |

### 11.4 外部系统接口

| 方法 | 端点 | 认证 | 请求参数 | 返回值 `data` 字段 | 描述 |
|------|------|------|----------|---------------------|------|
| GET | `/api/external/health` | API-Key | — | `{"status": str, "version": str}` | 对外健康检查 |
| GET | `/api/external/capabilities` | API-Key | — | `{"features": {...}}` | 查询外部 API 功能清单 |
| GET | `/api/external/account-status` | API-Key | `?email=` | `{"status": str, ...}` | 查询邮箱账号状态 |

---

## 12. 无认证 / 基础设施

| 方法 | 端点 | 认证 | 请求参数 | 返回值 | 描述 |
|------|------|------|----------|--------|------|
| GET | `/healthz` | 无 | — | `ok` (纯文本) | 探活端点（Docker/负载均衡用） |
| GET | `/img/:filename` | 无 | `filename` (路径) | 图片文件 | 静态图片资源服务 |
| GET | `/favicon.ico` | 无 | — | ico 文件 | 网站图标 |

---

## API 索引 (路径速查)

```
GET     /login                          # 登录页面
POST    /login                          # 登录提交
GET     /logout                         # 登出
GET     /                               # 主 SPA 页面
GET     /healthz                        # 探活
GET     /favicon.ico                    # 网站图标
GET     /img/:filename                  # 静态图片

GET     /api/csrf-token                 # CSRF Token
GET     /api/bootstrap                  # 首屏引导
GET     /api/providers                  # 邮箱提供商列表

# 分组
GET     /api/groups                     # 分组列表
POST    /api/groups                     # 创建分组
GET     /api/groups/:id                 # 分组详情
PUT     /api/groups/:id                 # 更新分组
DELETE  /api/groups/:id                 # 删除分组
GET     /api/groups/:id/export          # 导出分组账号

# 标签
GET     /api/tags                       # 标签列表
POST    /api/tags                       # 创建标签
DELETE  /api/tags/:tag_id               # 删除标签

# 账号
GET     /api/accounts                   # 账号列表
POST    /api/accounts                   # 导入账号
GET     /api/accounts/search            # 搜索账号
GET     /api/accounts/export            # 导出全部
POST    /api/accounts/export-selected   # 导出选中
POST    /api/export/verify              # 导出验证
GET     /api/accounts/:id               # 账号详情
PUT     /api/accounts/:id               # 更新账号
DELETE  /api/accounts/:id               # 删除账号
PATCH   /api/accounts/:id/remark        # 更新备注
DELETE  /api/accounts/email/:email      # 按邮箱删除
POST    /api/accounts/batch-update-group    # 批量移动分组
POST    /api/accounts/batch-delete          # 批量删除
POST    /api/accounts/batch-update-status   # 批量更新状态
POST    /api/accounts/batch-notification-toggle  # 批量通知开关
POST    /api/accounts/tags                  # 批量管理标签
POST    /api/accounts/:id/telegram-toggle   # 单账号通知开关

# 刷新
POST    /api/accounts/:id/refresh       # 刷新单账号
POST    /api/accounts/:id/retry-refresh # 重试刷新
GET     /api/accounts/refresh-all       # 刷新全部 (SSE)
POST    /api/accounts/refresh-failed    # 刷新失败的
GET     /api/accounts/trigger-scheduled-refresh  # 触发定时刷新 (SSE)
POST    /api/accounts/refresh/selected  # 刷新选中 (SSE)
GET     /api/accounts/refresh-logs      # 全局刷新日志
GET     /api/accounts/:id/refresh-logs  # 单账号刷新日志
GET     /api/accounts/refresh-logs/failed   # 失败日志
GET     /api/accounts/invalid-token-candidates  # Token 失效候选
GET     /api/accounts/refresh-stats     # 刷新统计

# 邮件
POST    /api/emails/batch               # 批量拉取邮件
GET     /api/emails/:email_addr         # 邮件列表
GET     /api/emails/:email_addr/extract-verification  # 提取验证码
POST    /api/emails/delete              # 删除邮件
GET     /api/email/:email_addr/:message_id  # 邮件详情

# 临时邮箱
GET     /api/temp-emails                # 临时邮箱列表
GET     /api/temp-emails/options        # 注册选项
POST    /api/temp-emails/generate       # 生成临时邮箱
GET     /api/temp-emails/:email/extract-verification  # 提取验证码
DELETE  /api/temp-emails/:email         # 删除临时邮箱
GET     /api/temp-emails/:email/messages    # 邮件列表
GET     /api/temp-emails/:email/messages/:msg_id  # 邮件详情
DELETE  /api/temp-emails/:email/messages/:msg_id  # 删除邮件
DELETE  /api/temp-emails/:email/clear   # 清空邮件
POST    /api/temp-emails/:email/refresh # 刷新邮件

# 号池管理
GET     /api/pool-admin/accounts        # 池账号列表
POST    /api/pool-admin/accounts/:id/action  # 池账号操作

# 设置
GET     /api/settings                   # 获取设置
PUT     /api/settings                   # 更新设置
POST    /api/settings/validate-cron     # 校验 Cron
POST    /api/settings/telegram-test     # 测试 Telegram
POST    /api/settings/test-telegram-proxy   # 测试 Telegram 代理
POST    /api/settings/email-test        # 测试邮件通知
POST    /api/settings/webhook-test      # 测试 Webhook
POST    /api/settings/verification-ai-test  # 测试 AI 提取
POST    /api/settings/cf-worker-sync-domains  # 同步 CF 域名
GET     /api/settings/external-api-key/plaintext  # 获取 API Key

# 系统
GET     /api/scheduler/status           # 调度器状态
GET     /api/system/health              # 系统健康
GET     /api/system/diagnostics         # 系统诊断
GET     /api/system/upgrade-status      # 升级状态
GET     /api/system/version-check       # 版本检查
GET     /api/system/deployment-info     # 部署信息
POST    /api/system/trigger-update      # 触发更新
POST    /api/system/test-watchtower     # 测试 Watchtower
POST    /api/system/reload-plugins      # 重载插件

# 概览
GET     /api/overview/summary           # 总览
GET     /api/overview/verification      # 验证码统计
GET     /api/overview/verification-stats    # 同上
GET     /api/overview/external-api      # 对外 API 统计
GET     /api/overview/external-api-stats    # 同上
GET     /api/overview/pool              # 池统计
GET     /api/overview/pool-stats        # 同上
GET     /api/overview/activity          # 活动统计

# 审计
GET     /api/audit-logs                 # 审计日志

# 插件
GET     /api/plugins                    # 插件列表
POST    /api/plugins/install            # 安装插件
POST    /api/plugins/:name/uninstall    # 卸载插件
GET     /api/plugins/:name/config/schema    # 配置 Schema
GET     /api/plugins/:name/config       # 获取配置
POST    /api/plugins/:name/config       # 保存配置
POST    /api/plugins/:name/test-connection  # 测试连接

# Token 工具
GET     /token-tool                     # 工具页面
GET     /token-tool/callback            # OAuth 回调
POST    /api/token-tool/prepare         # 准备 OAuth
POST    /api/token-tool/exchange        # 兑换 Token
POST    /api/token-tool/save            # 保存到账号
GET     /api/token-tool/accounts        # 账号列表
GET     /api/token-tool/config          # 获取配置
POST    /api/token-tool/config          # 保存配置

# 外部 API (API-Key)
GET     /api/external/health            # 对外健康检查
GET     /api/external/capabilities      # 功能清单
GET     /api/external/account-status    # 账号状态
GET     /api/external/messages          # 邮件列表
GET     /api/external/messages/latest   # 最新邮件
GET     /api/external/messages/:id      # 邮件详情
GET     /api/external/messages/:id/raw  # 邮件原始内容
GET     /api/external/verification-code # 提取验证码
GET     /api/external/verification-link # 提取验证链接
GET     /api/external/wait-message      # 等待新邮件
GET     /api/external/probe/:id         # 异步探测状态
POST    /api/external/pool/claim-random # 池领取
POST    /api/external/pool/claim-release    # 池释放
POST    /api/external/pool/claim-complete   # 池完成
GET     /api/external/pool/stats        # 池统计
POST    /api/external/temp-emails/apply     # 申请临时邮箱
POST    /api/external/temp-emails/:token/finish  # 释放临时邮箱
```
