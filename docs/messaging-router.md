# 消息路由网关实现规格 (Messaging Router)

本文是 `docs/adr/0005-messaging-router-gateway.md` 的实现规格, 面向实现者
决策理由与被否方案见 ADR 与 `.agents/notes/proposed/feature/2026-11-02-messaging-router-gateway.md`
平台调研, 适配器接口, NapCat 内置引擎与既有 REST 路由仍以 `docs/messaging-plugins.md` 为准, 本文只描述在其之上新增的路由层

## 1. 目录与模块划分

分层方向保持 api -> server -> models, 私有实现放 `impl/`, 单个 py 文件不超过 300 行, 每个目录 2 到 5 个 py 文件, `__init__.py` 不计入

现状约束
- `server/src/hx_email/server/messaging/` 已有 engine, onebot, registry, store, types 共 5 个 py 文件, 已满, 路由层不能放进去
- `server/src/hx_email/api/impl/messaging/` 已有 5 个 py 文件, 同样已满
- `server/src/hx_email/models/` 已有 5 个迁移文件, 新表的迁移写进现有 `models/messaging.py`, 不新增文件

新增目录与文件

| 路径 | 职责 | 预计行数 |
| --- | --- | --- |
| `server/src/hx_email/server/router/types.py` | envelope, SessionRef, Route, Delivery, Cursor 等数据类与 `MessagingProvider` 协议 | 180 |
| `server/src/hx_email/server/router/facade.py` | 路由层唯一公开入口, 被 MCP 与 REST 共同调用 | 260 |
| `server/src/hx_email/server/router/registry.py` | provider 注册表, 按 platform 字符串查找 provider | 90 |
| `server/src/hx_email/server/router/hub.py` | 进程内订阅信号分发, 每订阅者有界队列 | 150 |
| `server/src/hx_email/server/router/impl/outbox.py` | 出站排队, 令牌桶整形, 退避重试, 风控熔断 | 260 |
| `server/src/hx_email/server/router/impl/store.py` | router_routes 与 router_outbox 读写, cursor 增量查询 | 280 |
| `server/src/hx_email/server/router/impl/envelope.py` | envelope 序列化, raw 大字段落盘, cursor 编解码 | 160 |
| `server/src/hx_email/server/router/providers/qq.py` | 包装现有 `OneBotAdapter` 与 `ingest_event` 的 QQ provider | 180 |
| `server/src/hx_email/server/router/providers/github.py` | GitHub App provider, webhook 解析与评论发送 | 260 |
| `server/src/hx_email/server/router/providers/impl/github_auth.py` | App JWT 签发与 installation token 缓存 | 140 |
| `server/src/hx_email/server/router/providers/impl/webhook_sign.py` | 入站 HMAC 校验与出站 webhook 签名 | 80 |
| `server/src/hx_email/api/impl/router/rest_routes.py` | `/api/v1/router` REST 兼容面 | 280 |
| `server/src/hx_email/api/impl/router/ingress_routes.py` | 平台回调入口 `/api/v1/router/ingress/...` | 120 |
| `server/src/hx_email/api/impl/router/mcp_server.py` | MCP tool 与 resource 定义, 挂载到 `/mcp` | 280 |
| `server/src/hx_email/api/impl/router/schemas.py` | 共享的 pydantic 入参模型, 同时导出 JSON Schema 给 MCP | 200 |

目录文件数核对
- `server/router/` 为 types, facade, registry, hub 共 4 个
- `server/router/impl/` 为 outbox, store, envelope 共 3 个
- `server/router/providers/` 为 qq, github 共 2 个
- `server/router/providers/impl/` 为 github_auth, webhook_sign 共 2 个
- `api/impl/router/` 为 rest_routes, ingress_routes, mcp_server, schemas 共 4 个

依赖规则
- `api/impl/router/*` 只 import `server/router/facade.py` 与 `server/router/types.py`
- `server/router/providers/qq.py` 可以 import `server/messaging/onebot.py`, `server/messaging/impl/events.py`, `server/messaging/store.py`, 反方向禁止
- `server/messaging/` 不 import `server/router/` 的任何东西
- 邮箱业务模块 (`server/mail/` 等) 与路由层互不 import

新增依赖
- `mcp` 官方 Python SDK, 用其 streamable HTTP 传输挂到 FastAPI
- `PyJWT[crypto]`, 只用于 GitHub App 的 RS256 JWT, 复用已有的 `cryptography`
- 不引入 Redis, 消息队列或机器人框架

## 2. 地址语法

source 与 sink 共用同一套地址, 统一叫 session 地址

| 平台 | 地址格式 | 示例 |
| --- | --- | --- |
| QQ 私聊 | `qq:<instance_id>:private:<user_id>` | `qq:3:private:10001` |
| QQ 群 | `qq:<instance_id>:group:<group_id>` | `qq:3:group:123456789` |
| GitHub 仓库 | `github:<instance_id>:repo:<owner>/<repo>` | `github:7:repo:hx/HX-Email` |
| GitHub issue 或 PR | `github:<instance_id>:issue:<owner>/<repo>#<number>` | `github:7:issue:hx/HX-Email#42` |

- 地址中的 `instance_id` 就是 `messaging_instances.id`, 天然实现会话粘性
- 仓库地址只能作为 source, 向仓库地址发送等价于建 issue, 需要在 payload 中带 `title`
- route 的 source 选择器允许前缀匹配, 例如 `qq:3:group:` 表示该账号下全部群

## 3. 统一 envelope

### 3.1 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 网关内全局 ID, 形如 `m_<messaging_messages.id>` |
| `cursor` | string | 读到这一条之后的续读位置 |
| `platform` | string | `qq`, `github` 等 |
| `instance_id` | integer | 所属账号实例 |
| `session` | string | session 地址 |
| `session_type` | string | `private`, `group`, `channel`, `repo`, `issue` |
| `direction` | string | `inbound` 或 `outbound` |
| `sender` | object | `{id, name, is_self}` |
| `text` | string | 纯文本正文, 富文本段落拍平, 非文本段落写成 `[image]` 这类占位 |
| `reply_to` | string | 被回复消息的 `platform_message_id`, 没有则为空串 |
| `platform_message_id` | string | 平台原生消息 ID, 入站去重键的一部分 |
| `attachments` | array | `{kind, url, name, size}` 列表, 只存引用不存内容 |
| `occurred_at` | string | 平台侧时间, ISO 8601 UTC |
| `received_at` | string | 网关落库时间, ISO 8601 UTC |
| `raw` | object 或 null | provider 私有原始载荷, 默认不返回, `include_raw=true` 时返回 |
| `raw_ref` | string | raw 超过 16 KB 时落盘的相对路径, 小于阈值时为空串 |

### 3.2 公共示例

```json
{
  "id": "m_10452",
  "cursor": "c1.3.10452",
  "platform": "qq",
  "instance_id": 3,
  "session": "qq:3:group:123456789",
  "session_type": "group",
  "direction": "inbound",
  "sender": {"id": "10001", "name": "alice", "is_self": false},
  "text": "今晚的发布推迟到 9 点",
  "reply_to": "",
  "platform_message_id": "1873992211",
  "attachments": [],
  "occurred_at": "2026-11-02T13:20:05Z",
  "received_at": "2026-11-02T13:20:05Z",
  "raw": null,
  "raw_ref": ""
}
```

### 3.3 QQ 映射 (OneBot 11 群消息事件)

| OneBot 字段 | envelope 字段 |
| --- | --- |
| `message_type="group"`, `group_id` | `session_type="group"`, `session="qq:<iid>:group:<group_id>"` |
| `user_id`, `sender.nickname` | `sender.id`, `sender.name` |
| `self_id == user_id` | `sender.is_self=true` |
| `message` 段落数组 | `text` 由现有 `_segments_text` 逻辑拍平, `image` 段落进入 `attachments` |
| `message` 中的 `reply` 段落 | `reply_to` |
| `message_id` | `platform_message_id` |
| `time` (Unix 秒) | `occurred_at` |

```json
{
  "raw": {
    "post_type": "message",
    "message_type": "group",
    "self_id": 20002,
    "user_id": 10001,
    "group_id": 123456789,
    "message_id": 1873992211,
    "time": 1793632805,
    "sender": {"nickname": "alice"},
    "message": [{"type": "text", "data": {"text": "今晚的发布推迟到 9 点"}}]
  },
  "session": "qq:3:group:123456789",
  "sender": {"id": "10001", "name": "alice", "is_self": false},
  "platform_message_id": "1873992211"
}
```

### 3.4 GitHub 映射 (issue_comment 事件)

| GitHub 字段 | envelope 字段 |
| --- | --- |
| `repository.full_name`, `issue.number` | `session="github:<iid>:issue:<full_name>#<number>"`, `session_type="issue"` |
| `comment.user.login`, `comment.user.id` | `sender.name`, `sender.id` |
| `comment.performed_via_github_app.id == 本 App` | `sender.is_self=true` |
| `comment.body` | `text` |
| `comment.id` | `platform_message_id` |
| `comment.created_at` | `occurred_at` |
| 请求头 `X-GitHub-Delivery` | 写入 `raw.delivery_id`, 作为第二道去重键 |

```json
{
  "platform": "github",
  "instance_id": 7,
  "session": "github:7:issue:hx/HX-Email#42",
  "session_type": "issue",
  "sender": {"id": "583231", "name": "octocat", "is_self": false},
  "text": "复现了, 附上日志",
  "platform_message_id": "2449601123",
  "occurred_at": "2026-11-02T13:31:40Z",
  "raw": {"action": "created", "delivery_id": "72d3162e-cc78-11e3-81ab-4c9367dc0958"}
}
```

`issues` 与 `pull_request` 的 `opened` 事件映射为一条以标题加正文为 `text` 的 envelope, `platform_message_id` 取 `issue:<id>` 或 `pr:<id>`, 其它 action 只更新会话元数据不产出消息

## 4. 数据模型增量

迁移全部写进现有 `server/src/hx_email/models/messaging.py` 的 `migrate_messaging_schema`

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_messaging_messages_platform_id
ON messaging_messages(instance_id, message_id) WHERE message_id <> '';

CREATE TABLE IF NOT EXISTS router_routes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  source_prefix TEXT NOT NULL,
  filter_json TEXT NOT NULL DEFAULT '{}',
  delivery TEXT NOT NULL,
  target_encrypted TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  ack_cursor INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT
);

CREATE TABLE IF NOT EXISTS router_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id INTEGER NOT NULL REFERENCES messaging_instances(id),
  kind TEXT NOT NULL,
  session TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL DEFAULT (datetime('now')),
  platform_message_id TEXT NOT NULL DEFAULT '',
  last_error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(instance_id, kind, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_router_outbox_due
ON router_outbox(status, next_attempt_at);
```

- `router_outbox.kind` 为 `send` 或 `webhook`, 前者是平台出站, 后者是向外部 URL 投递 envelope
- `status` 取值 `queued`, `sending`, `sent`, `failed`, `dead`, `held`, 其中 `held` 表示风控熔断暂停
- 唯一索引建立前, 迁移先按 `(instance_id, message_id)` 保留最小 id 删除重复行
- `delivery` 取值 `mcp`, `sse`, `webhook`, `poll`

## 5. MCP tool 清单

MCP server 名为 `hx-router`, 传输为 streamable HTTP (`/mcp`) 与 stdio (`hx-email mcp`), 每个调用都以路由 API Key 绑定到一个用户
所有 tool 失败时返回 MCP 标准 `isError=true`, 内容中带 `{code, message}`, `code` 取值见第 9 节

### 5.1 `sources_list`

列出当前用户可用的平台, 账号实例及其在线与熔断状态

```json
{"type": "object", "properties": {"platform": {"type": "string", "description": "只看某个平台, 例如 qq"}}, "additionalProperties": false}
```

返回 `{"sources": [{"platform": "qq", "instance_id": 3, "name": "运维小号", "state": "online", "account_id": "20002", "outbound": "open", "risk_level": "third_party"}]}`, 其中 `outbound` 取 `open`, `held`, `manual_hold`

### 5.2 `sessions_list`

列出某个账号实例下可以监听与发送的会话

```json
{"type": "object", "properties": {"instance_id": {"type": "integer"}, "session_type": {"type": "string", "enum": ["private", "group", "channel", "repo", "issue"]}, "query": {"type": "string", "description": "按名称模糊过滤"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50}}, "required": ["instance_id"], "additionalProperties": false}
```

返回 `{"sessions": [{"session": "qq:3:group:123456789", "session_type": "group", "title": "发布群", "last_cursor": "c1.3.10452"}]}`

### 5.3 `session_select`

选定一个会话并返回它的元数据与当前游标, 作为后续 pull 与 subscribe 的起点

```json
{"type": "object", "properties": {"session": {"type": "string", "description": "session 地址"}, "from": {"type": "string", "enum": ["now", "earliest"], "default": "now"}}, "required": ["session"], "additionalProperties": false}
```

返回 `{"session": "qq:3:group:123456789", "title": "发布群", "can_send": true, "cursor": "c1.3.10452", "limits": {"per_session_interval_seconds": 3.0, "per_account_per_minute": 20}}`, `from="now"` 时 cursor 指向最新一条之后

### 5.4 `messages_pull`

按 cursor 读取一个会话或一个前缀下的增量消息, 同步, 只读数据库

```json
{"type": "object", "properties": {"source": {"type": "string", "description": "session 地址或地址前缀"}, "cursor": {"type": "string", "description": "上次返回的 next_cursor, 为空则从 session_select 给出的位置读"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50}, "direction": {"type": "string", "enum": ["inbound", "outbound", "both"], "default": "inbound"}, "include_raw": {"type": "boolean", "default": false}}, "required": ["source", "cursor"], "additionalProperties": false}
```

返回 `{"messages": [<envelope>], "next_cursor": "c1.3.10460", "has_more": false}`, 消息按 cursor 升序

### 5.5 `message_send`

向一个 sink 发送消息, 写入 outbox, 在整形器允许时同步投递并等待结果

```json
{"type": "object", "properties": {"sink": {"type": "string", "description": "session 地址"}, "text": {"type": "string", "minLength": 1, "maxLength": 4000}, "title": {"type": "string", "description": "只在向 GitHub 仓库地址建 issue 时必填"}, "reply_to": {"type": "string", "default": ""}, "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 64}, "wait_seconds": {"type": "number", "minimum": 0, "maximum": 5, "default": 5}}, "required": ["sink", "text", "idempotency_key"], "additionalProperties": false}
```

返回 `{"delivery_id": "d_881", "status": "sent", "platform_message_id": "1873992260", "queued_until": ""}`, 被整形推迟时 `status="queued"` 且 `queued_until` 给出预计投递时间

### 5.6 `delivery_status`

查询一次发送或一次 webhook 投递的状态

```json
{"type": "object", "properties": {"delivery_id": {"type": "string"}, "idempotency_key": {"type": "string"}, "sink": {"type": "string"}}, "oneOf": [{"required": ["delivery_id"]}, {"required": ["idempotency_key", "sink"]}], "additionalProperties": false}
```

返回 `{"delivery_id": "d_881", "status": "sent", "attempts": 1, "platform_message_id": "1873992260", "last_error": "", "updated_at": "2026-11-02T13:21:00Z"}`

### 5.7 `route_subscribe`

创建一条订阅规则, 让某个 source 前缀的新消息推送给当前 MCP 会话, SSE 或外部 webhook

```json
{"type": "object", "properties": {"source": {"type": "string", "description": "session 地址或前缀"}, "delivery": {"type": "string", "enum": ["mcp", "sse", "webhook", "poll"], "default": "mcp"}, "webhook_url": {"type": "string", "format": "uri"}, "filter": {"type": "object", "properties": {"sender_ids": {"type": "array", "items": {"type": "string"}}, "keywords": {"type": "array", "items": {"type": "string"}}, "exclude_self": {"type": "boolean", "default": true}}, "additionalProperties": false}, "from_cursor": {"type": "string"}, "ttl_seconds": {"type": "integer", "minimum": 60, "maximum": 2592000}}, "required": ["source"], "additionalProperties": false}
```

返回 `{"route_id": "r_12", "resource_uri": "hx-router://routes/r_12", "cursor": "c1.3.10452", "webhook_secret": "只在 delivery=webhook 时返回一次"}`, `delivery="mcp"` 时服务端自动对 `resource_uri` 执行 `resources/subscribe`

### 5.8 `route_unsubscribe`

删除一条订阅规则并释放它的信号队列

```json
{"type": "object", "properties": {"route_id": {"type": "string"}}, "required": ["route_id"], "additionalProperties": false}
```

返回 `{"route_id": "r_12", "removed": true}`

### 5.9 `routes_list`

列出当前用户的订阅规则及其积压情况

```json
{"type": "object", "properties": {"status": {"type": "string", "enum": ["active", "paused_backlog", "expired", "all"], "default": "active"}}, "additionalProperties": false}
```

返回 `{"routes": [{"route_id": "r_12", "source": "qq:3:group:", "delivery": "mcp", "status": "active", "ack_cursor": "c1.3.10452", "backlog": 0, "expires_at": ""}]}`

### 5.10 `events_wait`

长轮询, 阻塞到某条订阅有新数据或超时, 给不支持 resource 订阅的 MCP 客户端使用

```json
{"type": "object", "properties": {"route_id": {"type": "string"}, "cursor": {"type": "string"}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 55, "default": 25}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20}}, "required": ["route_id", "cursor"], "additionalProperties": false}
```

返回 `{"messages": [<envelope>], "next_cursor": "c1.3.10461", "gap": false, "timed_out": false}`, 等待期间不占用线程, 由 `hub.py` 的 asyncio 条件变量唤醒

### 5.11 `route_ack`

确认某条订阅已经处理到某个 cursor, 服务重启后按此续推

```json
{"type": "object", "properties": {"route_id": {"type": "string"}, "cursor": {"type": "string"}}, "required": ["route_id", "cursor"], "additionalProperties": false}
```

返回 `{"route_id": "r_12", "ack_cursor": "c1.3.10461"}`

### 5.12 MCP resource

- `hx-router://routes/{route_id}` 读取返回该 route 自 `ack_cursor` 之后的至多 50 条 envelope
- 有新数据时服务端发 `notifications/resources/updated`, 客户端再调用 `resources/read` 或 `messages_pull`
- 通知是提示不是数据, 丢失通知不会丢数据

## 6. REST 兼容面

前缀 `/api/v1/router`, 鉴权统一为 `Authorization: Bearer <路由 API Key>`, 前端会话 Cookie 同样被接受, 平台回调入口例外

| 方法 | 路径 | 入参 | 返回 | 鉴权 | 对应 MCP tool |
| --- | --- | --- | --- | --- | --- |
| GET | `/sources` | query `platform` | 同 `sources_list` | API Key | `sources_list` |
| GET | `/instances/{instance_id}/sessions` | query `session_type`, `query`, `limit` | 同 `sessions_list` | API Key | `sessions_list` |
| POST | `/sessions/select` | body 同 `session_select` | 同 `session_select` | API Key | `session_select` |
| GET | `/messages` | query `source`, `cursor`, `limit`, `direction`, `include_raw` | 同 `messages_pull` | API Key | `messages_pull` |
| POST | `/messages` | body 同 `message_send`, 也可用 `Idempotency-Key` 头代替 `idempotency_key` | 同 `message_send`, 排队时 HTTP 202 | API Key | `message_send` |
| GET | `/deliveries/{delivery_id}` | 无 | 同 `delivery_status` | API Key | `delivery_status` |
| POST | `/routes` | body 同 `route_subscribe` | 同 `route_subscribe`, HTTP 201 | API Key | `route_subscribe` |
| DELETE | `/routes/{route_id}` | 无 | 同 `route_unsubscribe` | API Key | `route_unsubscribe` |
| GET | `/routes` | query `status` | 同 `routes_list` | API Key | `routes_list` |
| GET | `/routes/{route_id}/wait` | query `cursor`, `timeout_seconds`, `limit` | 同 `events_wait` | API Key | `events_wait` |
| POST | `/routes/{route_id}/ack` | body `{cursor}` | 同 `route_ack` | API Key | `route_ack` |
| GET | `/routes/{route_id}/stream` | 头 `Last-Event-ID` 为 cursor | `text/event-stream`, 每帧 `id` 为 cursor | API Key | 对应 resource 订阅 |
| POST | `/ingress/qq/{instance_id}` | OneBot 11 事件 | `{stored}` | `X-Messaging-Token` | 无 |
| POST | `/ingress/github/{instance_id}` | GitHub webhook | `{stored}` | `X-Hub-Signature-256` | 无 |

- 现有 `POST /api/v1/messaging/events/{kind}` 保留, 内部改为转发到同一套 ingress 处理, NapCat 配置不需要立即变更
- 现有 `POST /api/v1/messaging/instances/{id}/send` 保留给前端, 内部改为调用 `facade.send` 以共享整形与幂等
- SSE 每 25 秒发送一次注释心跳 `:`, 只在有活跃 SSE 连接时存在, 无连接时没有任何定时器

出站 webhook 投递格式
- `POST <webhook_url>`, body 为 `{"route_id", "messages": [<envelope>], "next_cursor"}`
- 头 `X-HX-Router-Signature: sha256=<hex>`, 以 route 创建时返回的 `webhook_secret` 做 HMAC-SHA256
- 头 `X-HX-Router-Delivery: <delivery_id>`, 接收方据此去重
- 接收方返回 2xx 视为成功并推进该 route 的 `ack_cursor`

## 7. cursor 语义与一致性边界

- cursor 格式为 `c1.<instance_id>.<messaging_messages.id>`, 跨实例前缀订阅使用 `c1.0.<id>` 表示全局位置, 对调用方保持不透明
- `messaging_messages.id` 是 SQLite 自增主键, 只在单写者单实例部署下保证单调, 这与 ADR 0002 的部署形态一致
- 读取语义为 `WHERE id > <cursor_id> ORDER BY id ASC LIMIT n`, 走 `(instance_id, chat_id, id)` 索引
- 投递语义为至少一次, 推送, SSE, webhook 都可能重复, 消费者以 envelope 的 `id` 去重
- 入站去重键为 `(instance_id, platform_message_id)`, GitHub 额外用 `X-GitHub-Delivery` 在 ingress 层做一次短期去重, 两者都命中时直接返回 `stored=false`
- 出站去重键为 `(instance_id, kind, idempotency_key)`, 重复请求返回首次的 `delivery_id` 与当前状态
- 重启续读: route 的 `ack_cursor` 持久化在 `router_routes`, 进程启动后 SSE 与 webhook 从 `ack_cursor` 续推, MCP 客户端重连后用自己保存的 cursor 调 `messages_pull`
- 重启时 `router_outbox` 中处于 `sending` 的行回退为 `queued` 并增加 attempts, 由于平台侧可能已经收到, 这是唯一可能出现重复出站的窗口, QQ 与 GitHub 都没有平台侧幂等键, 规格接受这一窗口并在 `delivery_status` 中以 `attempts>1` 暴露
- 一致性边界: 同一 session 内按 id 有序, 跨 session 只保证每条最终可读, 不保证全局因果序

## 8. 配置与密钥存储

所有密钥都进入 `messaging_instances.config_encrypted`, 整体 JSON 用 `security.encrypt_secret(settings, value)` 加密, 读取用 `security.decrypt_secret`

| 配置键 | 平台 | 说明 | API 返回 |
| --- | --- | --- | --- |
| `event_token` | QQ | NapCat 上报时携带的 `X-Messaging-Token`, 沿用现有生成逻辑 | `***` |
| `api_base_url` | QQ | 内置引擎容器的 OneBot HTTP 地址 | 原值 |
| `rate_profile` | QQ | `conservative` 或 `default`, 决定令牌桶参数 | 原值 |
| `app_id` | GitHub | GitHub App ID | 原值 |
| `installation_id` | GitHub | 安装 ID | 原值 |
| `private_key_pem` | GitHub | App 私钥 PEM 全文 | `***` |
| `webhook_secret` | GitHub | App webhook secret | `***` |

- route 的外部 webhook URL 与其 `webhook_secret` 加密存入 `router_routes.target_encrypted`
- 路由 API Key 只存 SHA-256 哈希, 明文只在创建时返回一次
- GitHub installation token 只在内存缓存, 不落库, 进程重启后重新换取
- `.env` 与日志中不出现任何上述明文, 日志里的 session 地址保留, 消息 `text` 默认不写日志

## 9. 速率整形与错误码

QQ 默认参数对应 `rate_profile=default`
- 同一 session 最小间隔 3 秒, 账号级每分钟 20 条, 突发 3 条, 每日 1000 条, 每次附加 0.5 到 1.5 秒抖动
- `conservative` 档为同一 session 最小间隔 6 秒, 账号级每分钟 8 条, 每日 300 条

GitHub 默认参数
- 账号级每分钟 30 次写操作, 突发 5 次, 不设每日上限

| code | 含义 | 是否可重试 |
| --- | --- | --- |
| `session_not_found` | 地址无效或不属于当前用户 | 否 |
| `session_not_sendable` | 仓库地址缺少 title, 或 QQ 目标不在好友与群列表中 | 否 |
| `rate_limited` | 本地整形拒绝且 `wait_seconds` 内无法投递, 消息已入队 | 不需要, 已排队 |
| `outbound_held` | 账号处于风控熔断或人工暂停 | 否, 恢复后自动继续 |
| `provider_offline` | 账号实例离线 | 是 |
| `provider_error` | 平台返回错误 | 视 `retryable` |
| `cursor_invalid` | cursor 无法解析或属于其它实例 | 否 |

## 10. 分阶段落地

### 阶段 1: QQ 收发与 GitHub 事件监听

- 范围: `server/router/` 骨架, QQ provider, GitHub provider 的入站部分, `messages_pull`, `message_send` (仅 QQ), `sources_list`, `sessions_list`, `session_select`, `delivery_status`, 去重唯一索引与 outbox 表
- 里程碑: 用 MCP Inspector 连接 `/mcp`, 选定一个 QQ 群, 调用 `message_send` 发出消息并在 QQ 客户端看到, 群里回复后用返回的 cursor 调 `messages_pull` 只读到这条回复, 对测试仓库评论后同样能 pull 到对应 envelope
- 验收: 同一 `idempotency_key` 调用两次只发出一条, NapCat 重投同一事件只落库一行, 连发 5 条时相邻两条的发送间隔不小于 3 秒

### 阶段 2: 订阅与推送

- 范围: `hub.py`, `route_subscribe`, `route_unsubscribe`, `routes_list`, `events_wait`, `route_ack`, MCP resource 通知, SSE 流, REST 兼容面全部路由
- 里程碑: MCP 客户端订阅一个 QQ 群后, 群内新消息在 1 秒内触发 `notifications/resources/updated`, 断开重连后从 `ack_cursor` 续读无遗漏
- 验收: ADR 0005 的 A1, A2, A3, A6 全部通过

### 阶段 3: 出站 webhook 与 GitHub 发送

- 范围: webhook 类型 route 及其签名与退避, GitHub provider 的评论与建 issue, 风控熔断
- 里程碑: 一条 webhook route 把 QQ 群消息投递到外部接收端并通过签名校验, 接收端停机 1 小时后恢复, 积压消息按序补投, 通过 MCP 对 issue 发评论并在 GitHub 上看到由 App 身份发出
- 验收: ADR 0005 的 A4, A5 通过, 模拟 OneBot 频率类错误后该账号出站进入 `held` 并在 30 分钟后自动恢复

### 阶段 4: 前端切换与新平台

- 范围: 现有前端消息页改用 cursor 读取, `registry.py` 中 QQ 描述与 NapCat 实际路径对齐, 按需新增 Telegram 或企业微信 provider
- 里程碑: 新增一个 provider 的变更只涉及 `server/router/providers/` 与注册表一行, `server/router/` 其余文件零改动
- 验收: 新 provider 的 pull 与 send 通过阶段 1 的同一套用例

## 11. 测试清单

- `server/tests/test_router_cursor.py` 覆盖 cursor 编解码, 增量读, 越界与跨实例 cursor 拒绝
- `server/tests/test_router_outbox.py` 覆盖幂等, 令牌桶间隔, 退避次数上限, 熔断与恢复, 重启时 sending 回退
- `server/tests/test_router_ingress.py` 覆盖 OneBot 事件去重, GitHub 签名校验失败返回 401, delivery 去重
- `server/tests/test_router_mcp.py` 用 MCP SDK 的内存传输调用全部 tool, 校验入参 schema 拒绝多余字段
- `server/tests/test_router_idle.py` 在 CI 中只校验 "无订阅时没有除 housekeeping 外的定时任务", 真实 CPU 与内存验收项 A1 到 A6 在部署机上手工执行并记录到实现 note
