# HX-Email API 文档

> 所有接口均基于 FastAPI, Base URL 为配置的服务器地址。
> 认证方式: `Authorization: Bearer <token>` (除登录/注册/健康检查外均需携带)。

---

## 目录

- [1. 系统接口](#1-系统接口)
- [2. 认证接口](#2-认证接口)
- [3. 工作台接口](#3-工作台接口)
- [4. 平台接口](#4-平台接口)
- [5. 可用邮箱接口](#5-可用邮箱接口)
- [6. 邮箱池接口](#6-邮箱池接口)
- [7. 邮箱账户接口](#7-邮箱账户接口)
- [8. 临时邮箱接口](#8-临时邮箱接口)

---

## 1. 系统接口

### GET /health

**描述**: 健康检查, 用于监控/负载均衡探活。

- **认证**: 无
- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "status": "ok",
  "service": "hx-email"
}
```

---

### GET /data/export

**描述**: 导出当前用户的所有核心数据 (邮箱账户、可用邮箱、分组、标签、平台、绑定关系等)。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "version": 1,
  "email_accounts": [{ "id": 1, "provider": "gmail", "primary_address": "a@b.com", ... }],
  "usable_emails": [{ "id": 1, "address": "x@y.com", "label": "主邮箱", ... }],
  "groups": [{ "id": 1, "name": "Work", "color": "#58a6ff" }],
  "tags": [{ "id": 1, "name": "重要", "color": "#238636" }],
  "usable_email_tags": [{ "usable_email_id": 1, "tag_id": 1 }],
  "platforms": [{ "id": 1, "name": "GitHub" }],
  "platform_bindings": [{ "id": 1, "usable_email_id": 1, "platform_id": 1, "status": "active", "notes": "" }],
  "deferred_capabilities": []
}
```

---

### POST /data/import

**描述**: 导入数据到当前用户账户 (格式与 `/data/export` 输出一致)。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**: 与 `/data/export` 返回值结构一致
```json
{
  "email_accounts": [...],
  "usable_emails": [...],
  "groups": [...],
  "tags": [...],
  "usable_email_tags": [...],
  "platforms": [...],
  "platform_bindings": [...]
}
```

**返回值** (201 Created): 与 `/data/export` 返回值相同 (导入后的重新导出)

**错误**:
| 状态码 | 说明 |
|--------|------|
| 409 | 导入数据与已有数据冲突 |

---

## 2. 认证接口

### POST /auth/login

**描述**: 用户名密码登录, 返回访问令牌。

- **认证**: 无
- **请求参数**: 无
- **请求体**:
```json
{
  "username": "string",
  "password": "string"
}
```

**返回值** (200):
```json
{
  "access_token": "eyJ...",
  "user": {
    "id": 1,
    "username": "admin",
    "is_admin": true
  }
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 401 | 用户名或密码错误 `{"detail": "Invalid username or password"}` |

---

### POST /auth/register

**描述**: 注册新用户账户 (非管理员), 注册后直接返回令牌。

- **认证**: 无
- **请求参数**: 无
- **请求体**:
```json
{
  "username": "string",
  "password": "string"
}
```

**返回值** (201 Created):
```json
{
  "access_token": "eyJ...",
  "user": {
    "id": 2,
    "username": "new_user",
    "is_admin": false
  }
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 403 | 注册功能已关闭 `{"detail": "Registration disabled"}` |

---

### POST /auth/logout

**描述**: 注销当前会话, 撤销令牌。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**: 无

**返回值**: 204 No Content (空 body)

---

### PUT /auth/me/credentials

**描述**: 更新当前用户的用户名和密码。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**:
```json
{
  "username": "string",
  "password": "string"
}
```

**返回值** (200):
```json
{
  "user": {
    "id": 1,
    "username": "new_name",
    "is_admin": false
  }
}
```

---

### PUT /admin/settings/registration

**描述**: 管理员切换注册开关。

- **认证**: Bearer Token (管理员)
- **请求参数**: 无
- **请求体**:
```json
{
  "enabled": true
}
```

**返回值** (200):
```json
{
  "registration_enabled": true
}
```

---

## 3. 工作台接口

### GET /workbench/overview

**描述**: 获取工作台仪表盘统计数据。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "usable_email_count": 10,
  "active_email_count": 8,
  "account_count": 3,
  "temp_email_count": 2,
  "platform_count": 5,
  "binding_count": 12,
  "pool_available_count": 3,
  "pool_claimed_count": 1,
  "verification_count": 4
}
```

---

### POST /groups

**描述**: 创建新分组 (用于组织可用邮箱)。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**:
```json
{
  "name": "string",
  "color": "string"       // 可选, 默认 "#58a6ff"
}
```

**返回值** (201 Created):
```json
{
  "id": 1,
  "name": "Work",
  "color": "#58a6ff"
}
```

---

### POST /tags

**描述**: 创建新标签 (用于标记可用邮箱)。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**:
```json
{
  "name": "string",
  "color": "string"       // 可选, 默认 "#238636"
}
```

**返回值** (201 Created):
```json
{
  "id": 1,
  "name": "重要",
  "color": "#238636"
}
```

---

### GET /workbench/usable-emails

**描述**: 分页查询可用邮箱列表, 支持多维筛选 (用于工作台主视图)。

- **认证**: Bearer Token
- **请求参数** (Query, 全部可选):

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `kind` | str | - | 按类型筛选: `custom`, `primary`, `alias`, `temp` |
| `status` | str | - | 按状态筛选: `active`, `inactive`, `archived` |
| `group_id` | int | - | 按分组 ID 筛选 |
| `tag_id` | int | - | 按标签 ID 筛选 |
| `keyword` | str | - | 模糊搜索 address 和 label |
| `platform_binding` | str | - | `bound` 已绑定 / `unbound` 未绑定 |
| `page` | int | 1 | 页码 |
| `page_size` | int | 50 | 每页条数 (最大 200) |

- **请求体**: 无

**返回值** (200):
```json
{
  "usable_emails": [
    {
      "id": 1,
      "address": "hello@example.com",
      "label": "主邮箱",
      "kind": "primary",
      "status": "active",
      "group": { "id": 1, "name": "Work", "color": "#58a6ff" },
      "tags": [
        { "id": 1, "name": "重要", "color": "#238636" }
      ],
      "platform_binding_count": 2
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 50
}
```

---

### PUT /usable-emails/{usable_email_id}/organize

**描述**: 整理可用邮箱 — 设置标签、分组和别名。

- **认证**: Bearer Token
- **路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `usable_email_id` | int | 可用邮箱 ID |

- **请求体** (所有字段可选):
```json
{
  "label": "string | null",
  "group_id": "int | null",
  "tag_ids": [1, 2, 3]
}
```

**返回值** (200): 与 `/workbench/usable-emails` 中单个邮箱结构一致

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 可用邮箱不存在或分组/标签 ID 无效 `{"detail": "Usable email not found"}` |

---

## 4. 平台接口

### POST /platforms

**描述**: 创建新平台 (如注册网站/服务)。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**:
```json
{
  "name": "string"
}
```

**返回值** (201 Created):
```json
{
  "id": 1,
  "name": "GitHub"
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 409 | 平台名称重复 `{"detail": "Platform name already exists"}` |

---

### GET /platforms

**描述**: 获取当前用户的所有平台列表, 支持按名称搜索。

- **认证**: Bearer Token
- **请求参数** (Query):

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | str | - | 按平台名称模糊搜索 |

- **请求体**: 无

**返回值** (200):
```json
{
  "platforms": [
    { "id": 1, "name": "GitHub" },
    { "id": 2, "name": "Twitter" }
  ]
}
```

---

### PUT /platforms/{platform_id}

**描述**: 更新平台名称。

- **认证**: Bearer Token
- **路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `platform_id` | int | 平台 ID |

- **请求体**:
```json
{
  "name": "string"
}
```

**返回值** (200):
```json
{
  "id": 1,
  "name": "GitHub (new)"
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 平台不存在 `{"detail": "Platform not found"}` |
| 409 | 平台名称重复 `{"detail": "Platform name already exists"}` |

---

### POST /platform-candidates

**描述**: 根据邮件信息智能推测平台候选名称 (提取发件人邮箱域名)。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体** (所有字段可选, 默认空字符串):
```json
{
  "sender": "noreply@github.com",
  "subject": "Verify your email",
  "body": "..."
}
```

**返回值** (200):
```json
{
  "platform_candidates": [
    { "name": "github.com", "source": "sender_domain" }
  ]
}
```

---

### POST /usable-emails/{usable_email_id}/platform-bindings

**描述**: 将可用邮箱绑定到平台。

- **认证**: Bearer Token
- **路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `usable_email_id` | int | 可用邮箱 ID |

- **请求体**:
```json
{
  "platform_id": 1,
  "status": "active",           // active | pending_verification | risk | disabled | archived, 默认 "active"
  "notes": "string"             // 可选, 默认 ""
}
```

**返回值** (201 Created):
```json
{
  "id": 1,
  "usable_email_id": 1,
  "platform": { "id": 1, "name": "GitHub" },
  "status": "active",
  "notes": "主账号"
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 可用邮箱或平台不存在 |
| 409 | 绑定已存在 `{"detail": "Platform binding already exists"}` |
| 422 | 绑定状态值无效 `{"detail": "Invalid platform binding status"}` |

---

### GET /usable-emails/{usable_email_id}/platform-bindings

**描述**: 获取某个可用邮箱的所有平台绑定。

- **认证**: Bearer Token
- **路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `usable_email_id` | int | 可用邮箱 ID |

- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "platform_bindings": [
    {
      "id": 1,
      "usable_email_id": 1,
      "platform": { "id": 1, "name": "GitHub" },
      "status": "active",
      "notes": "主账号"
    }
  ]
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 可用邮箱不存在 `{"detail": "Usable email not found"}` |

---

### PUT /platform-bindings/{binding_id}

**描述**: 更新平台绑定的状态和备注。

- **认证**: Bearer Token
- **路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `binding_id` | int | 平台绑定 ID |

- **请求体**:
```json
{
  "status": "disabled",
  "notes": "已停用"
}
```

**返回值** (200): 与平台绑定对象结构一致 (参见 POST 创建绑定返回值)

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 绑定不存在 `{"detail": "Platform binding not found"}` |
| 422 | 绑定状态值无效 `{"detail": "Invalid platform binding status"}` |

---

## 5. 可用邮箱接口

### POST /usable-emails

**描述**: 创建自定义可用邮箱记录 (kind="custom")。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**:
```json
{
  "address": "my@custom.com",
  "label": "自定义邮箱"         // 可选, 默认 ""
}
```

**返回值** (201 Created):
```json
{
  "id": 1,
  "address": "my@custom.com",
  "label": "自定义邮箱",
  "kind": "custom",
  "status": "active"
}
```

---

### GET /usable-emails

**描述**: 获取当前用户所有活跃的可用邮箱列表。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "usable_emails": [
    {
      "id": 1,
      "address": "hello@example.com",
      "label": "主邮箱",
      "kind": "primary",
      "status": "active"
    }
  ]
}
```

---

### GET /usable-emails/{usable_email_id}

**描述**: 获取单个可用邮箱详情。

- **认证**: Bearer Token
- **路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `usable_email_id` | int | 可用邮箱 ID |

- **请求参数**: 无
- **请求体**: 无

**返回值** (200): 同上单个邮箱结构

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 可用邮箱不存在 `{"detail": "Usable email not found"}` |

---

### POST /usable-emails/{usable_email_id}/deactivate

**描述**: 停用可用邮箱 (设 status 为 "inactive")。

- **认证**: Bearer Token
- **路径参数**: `usable_email_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200): 邮箱对象 (status 变为 "inactive")

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 可用邮箱不存在 `{"detail": "Usable email not found"}` |

---

### POST /usable-emails/{usable_email_id}/verification/read

**描述**: 读取邮箱的收件箱, 扫描验证码和验证链接, 保存结果到历史。

- **认证**: Bearer Token
- **路径参数**: `usable_email_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "usable_email": {
    "id": 1,
    "address": "hello@example.com",
    "label": "主邮箱",
    "kind": "primary",
    "status": "active"
  },
  "matches": [
    {
      "code": "123456",
      "link": "https://example.com/verify?token=xxx",
      "recipient_address": "hello@example.com",
      "certainty": "high",
      "subject": "Verify your email address"
    }
  ]
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 可用邮箱不存在 `{"detail": "Usable email not found"}` |

---

### GET /usable-emails/{usable_email_id}/verification/history

**描述**: 获取验证历史记录 (从数据库读取, 不重新扫描邮箱)。

- **认证**: Bearer Token
- **路径参数**: `usable_email_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200): 同上 (验证读取返回值结构)

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 可用邮箱不存在 `{"detail": "Usable email not found"}` |

---

## 6. 邮箱池接口

### POST /mail-pool/entries

**描述**: 将可用邮箱加入邮箱池, 状态变为 "available"。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**:
```json
{
  "usable_email_id": 1
}
```

**返回值** (201 Created):
```json
{
  "id": 1,
  "usable_email": {
    "id": 1,
    "address": "hello@example.com",
    "label": "主邮箱",
    "kind": "primary",
    "status": "active"
  },
  "status": "available",
  "claim_key": "abc123",
  "claimed_project_key": "",
  "completed_project_key": ""
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 可用邮箱不存在 `{"detail": "Usable email not found"}` |
| 409 | 邮箱已在池中 `{"detail": "Usable email is already in the mail pool"}` |

---

### GET /mail-pool/entries

**描述**: 获取当前用户所有邮箱池条目。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "entries": [
    { /* MailPoolEntry 对象, 结构同上 */ }
  ]
}
```

---

### POST /mail-pool/claim

**描述**: 为某个项目领取一个可用的邮箱池条目。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**:
```json
{
  "project_key": "my-project",
  "claim_key": ""               // 可选, 默认 ""
}
```

**返回值** (200): MailPoolEntry 对象 (status 变为 "claimed", project_key 被记录)

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 没有可用邮箱 `{"detail": "No usable email available"}` |

> 逻辑: 返回 status="available" 且 completed_project_key 不等于当前 project_key 的第一个条目。

---

### POST /mail-pool/entries/{usable_email_id}/release

**描述**: 将已领取的邮箱释放回可用池。

- **认证**: Bearer Token
- **路径参数**: `usable_email_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200): MailPoolEntry 对象 (status 重置为 "available", claim 信息清除)

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 邮箱池条目不存在 `{"detail": "Mail pool entry not found"}` |

---

### POST /mail-pool/entries/{usable_email_id}/complete

**描述**: 标记邮箱池条目为已完成 (用于某项目)。

- **认证**: Bearer Token
- **路径参数**: `usable_email_id` (int)
- **请求体**:
```json
{
  "project_key": "my-project"
}
```

**返回值** (200): MailPoolEntry 对象 (status 变为 "completed")

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 邮箱池条目不存在 `{"detail": "Mail pool entry not found"}` |

---

### POST /mail-pool/entries/{usable_email_id}/cooldown

**描述**: 将邮箱池条目置为冷却状态 (临时禁止被领取)。

- **认证**: Bearer Token
- **路径参数**: `usable_email_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200): MailPoolEntry 对象 (status 变为 "cooling")

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 邮箱池条目不存在 `{"detail": "Mail pool entry not found"}` |

---

## 7. 邮箱账户接口

### POST /email-accounts

**描述**: 添加邮箱账户 (含主地址和别名), 同时创建对应的 usable_email 记录。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**:
```json
{
  "provider": "gmail",
  "primary_address": "user@gmail.com",
  "display_name": "User",
  "imap_host": "",              // 可选, 默认 ""
  "imap_port": null,            // 可选, 默认 null
  "username": "",               // 可选, 默认 ""
  "alias_addresses": []         // 可选, 默认 []
}
```

**返回值** (201 Created):
```json
{
  "id": 1,
  "provider": "gmail",
  "primary_address": "user@gmail.com",
  "display_name": "User",
  "status": "active",
  "primary_usable_email": {
    "id": 1,
    "address": "user@gmail.com",
    "label": "User",
    "kind": "primary",
    "status": "active"
  },
  "usable_emails": [
    { "id": 1, "address": "user@gmail.com", "label": "User", "kind": "primary", "status": "active" },
    { "id": 2, "address": "alias@domain.com", "label": "别名", "kind": "alias", "status": "active" }
  ]
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 409 | 主地址已存在 `{"detail": "Email account primary address already exists for this user"}` |
| 409 | 可用邮箱地址已存在 `{"detail": "Usable email address already exists for this user"}` |
| 422 | 别名字段使用了 plus 子地址 `{"detail": "Alias address must be a real mailbox address"}` |

---

### GET /email-accounts

**描述**: 获取当前用户所有邮箱账户。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "email_accounts": [
    { /* EmailAccount 对象, 结构同上 */ }
  ]
}
```

---

### GET /email-accounts/{account_id}

**描述**: 获取单个邮箱账户详情。

- **认证**: Bearer Token
- **路径参数**: `account_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200): EmailAccount 对象 (结构同上)

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 邮箱账户不存在 `{"detail": "Email account not found"}` |

---

### POST /email-accounts/{account_id}/aliases

**描述**: 为已有邮箱账户添加新别名。

- **认证**: Bearer Token
- **路径参数**: `account_id` (int)
- **请求体**:
```json
{
  "address": "alias@domain.com",
  "label": "别名"              // 可选, 默认取 address
}
```

**返回值** (201 Created):
```json
{
  "id": 2,
  "address": "alias@domain.com",
  "label": "别名",
  "kind": "alias",
  "status": "active"
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 邮箱账户不存在 `{"detail": "Email account not found"}` |
| 409 | 地址重复 `{"detail": "Usable email address already exists for this user"}` |
| 422 | 使用了 plus 子地址 `{"detail": "Alias address must be a real mailbox address"}` |

---

### POST /email-accounts/{account_id}/deactivate

**描述**: 停用邮箱账户及其所有关联的可用邮箱。

- **认证**: Bearer Token
- **路径参数**: `account_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200): EmailAccount 对象 (status 变为 "inactive", 所有 usable_emails 也变为 inactive)

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 邮箱账户不存在 `{"detail": "Email account not found"}` |

---

## 8. 临时邮箱接口

### POST /temp-mail/cf/mailboxes

**描述**: 通过 Cloudflare 提供商创建临时邮箱。

- **认证**: Bearer Token
- **请求参数**: 无
- **请求体**:
```json
{
  "address": null,              // null = 自动生成地址; 也可指定
  "label": "临时用"
}
```

**返回值** (201 Created):
```json
{
  "id": 1,
  "address": "random@temp.example.com",
  "label": "临时用",
  "kind": "temp",
  "status": "active",
  "provider": "cf",
  "email_account_id": null
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 409 | 地址重复 `{"detail": "Usable email address already exists for this user"}` |
| 503 | CF 临时邮箱未配置 `{"detail": "CF temp mail provider not configured"}` |

---

### POST /temp-mail/{usable_email_id}/archive

**描述**: 归档临时邮箱 (status 变为 "archived")。

- **认证**: Bearer Token
- **路径参数**: `usable_email_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200): 临时邮箱对象 (status 变为 "archived")

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 临时邮箱不存在 `{"detail": "Temp mailbox not found"}` |

---

### GET /temp-mail/{usable_email_id}/messages

**描述**: 获取临时邮箱的所有消息。

- **认证**: Bearer Token
- **路径参数**: `usable_email_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "messages": [
    {
      "id": "msg_001",
      "from_address": "noreply@github.com",
      "subject": "Verify your email",
      "text": "Your code is 123456",
      "html": "<html>...</html>"
    }
  ]
}
```

**错误**:
| 状态码 | 说明 |
|--------|------|
| 404 | 临时邮箱不存在 `{"detail": "Temp mailbox not found"}` |
| 503 | 临时邮箱提供商未配置 `{"detail": "Temp mail provider is not configured: cf"}` |

---

### GET /temp-mail/{usable_email_id}/codes

**描述**: 提取临时邮箱中所有验证码 (4-8 位数字)。

- **认证**: Bearer Token
- **路径参数**: `usable_email_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "codes": [
    { "message_id": "msg_001", "code": "123456" }
  ]
}
```

**错误**: 同 `/temp-mail/{usable_email_id}/messages`

---

### GET /temp-mail/{usable_email_id}/verification-links

**描述**: 提取临时邮箱中所有 URL 链接。

- **认证**: Bearer Token
- **路径参数**: `usable_email_id` (int)
- **请求参数**: 无
- **请求体**: 无

**返回值** (200):
```json
{
  "links": [
    { "message_id": "msg_001", "url": "https://github.com/verify?token=xxx" }
  ]
}
```

**错误**: 同 `/temp-mail/{usable_email_id}/messages`

---

## 接口总览

| # | 方法 | 路径 | 认证 | 说明 |
|---|------|------|------|------|
| 1 | GET | `/health` | 无 | 健康检查 |
| 2 | GET | `/data/export` | 用户 | 导出全部数据 |
| 3 | POST | `/data/import` | 用户 | 导入数据 |
| 4 | POST | `/auth/login` | 无 | 登录 |
| 5 | POST | `/auth/register` | 无 | 注册 |
| 6 | POST | `/auth/logout` | 用户 | 注销 |
| 7 | PUT | `/auth/me/credentials` | 用户 | 修改密码 |
| 8 | PUT | `/admin/settings/registration` | 管理员 | 注册开关 |
| 9 | GET | `/workbench/overview` | 用户 | 工作台概览 |
| 10 | POST | `/groups` | 用户 | 创建分组 |
| 11 | POST | `/tags` | 用户 | 创建标签 |
| 12 | GET | `/workbench/usable-emails` | 用户 | 工作台邮箱列表 |
| 13 | PUT | `/usable-emails/{id}/organize` | 用户 | 整理邮箱 |
| 14 | POST | `/platforms` | 用户 | 创建平台 |
| 15 | GET | `/platforms` | 用户 | 平台列表 |
| 16 | PUT | `/platforms/{id}` | 用户 | 更新平台 |
| 17 | POST | `/platform-candidates` | 用户 | 智能推测平台 |
| 18 | POST | `/usable-emails/{id}/platform-bindings` | 用户 | 绑定平台 |
| 19 | GET | `/usable-emails/{id}/platform-bindings` | 用户 | 查看绑定 |
| 20 | PUT | `/platform-bindings/{id}` | 用户 | 更新绑定 |
| 21 | POST | `/usable-emails` | 用户 | 创建自定义邮箱 |
| 22 | GET | `/usable-emails` | 用户 | 可用邮箱列表 |
| 23 | GET | `/usable-emails/{id}` | 用户 | 可用邮箱详情 |
| 24 | POST | `/usable-emails/{id}/deactivate` | 用户 | 停用邮箱 |
| 25 | POST | `/usable-emails/{id}/verification/read` | 用户 | 读取验证码 |
| 26 | GET | `/usable-emails/{id}/verification/history` | 用户 | 验证历史 |
| 27 | POST | `/mail-pool/entries` | 用户 | 加入邮箱池 |
| 28 | GET | `/mail-pool/entries` | 用户 | 邮箱池列表 |
| 29 | POST | `/mail-pool/claim` | 用户 | 领取邮箱 |
| 30 | POST | `/mail-pool/entries/{id}/release` | 用户 | 释放邮箱 |
| 31 | POST | `/mail-pool/entries/{id}/complete` | 用户 | 完成使用 |
| 32 | POST | `/mail-pool/entries/{id}/cooldown` | 用户 | 冷却邮箱 |
| 33 | POST | `/email-accounts` | 用户 | 添加邮箱账户 |
| 34 | GET | `/email-accounts` | 用户 | 邮箱账户列表 |
| 35 | GET | `/email-accounts/{id}` | 用户 | 邮箱账户详情 |
| 36 | POST | `/email-accounts/{id}/aliases` | 用户 | 添加别名 |
| 37 | POST | `/email-accounts/{id}/deactivate` | 用户 | 停用账户 |
| 38 | POST | `/temp-mail/cf/mailboxes` | 用户 | 创建临时邮箱 |
| 39 | POST | `/temp-mail/{id}/archive` | 用户 | 归档临时邮箱 |
| 40 | GET | `/temp-mail/{id}/messages` | 用户 | 查看消息 |
| 41 | GET | `/temp-mail/{id}/codes` | 用户 | 提取验证码 |
| 42 | GET | `/temp-mail/{id}/verification-links` | 用户 | 提取验证链接 |

---

> 共 **42 个接口**。3 个系统接口, 5 个认证接口, 5 个工作台接口, 7 个平台接口, 6 个可用邮箱接口, 6 个邮箱池接口, 5 个邮箱账户接口, 5 个临时邮箱接口。
