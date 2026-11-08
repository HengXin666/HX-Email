# 消息路由网关实现规格 (Messaging Router)

本文是 `docs/adr/0005-messaging-router-gateway.md` 的实现规格, 面向实现者
本文是消息路由全套文档的唯一契约: 会话地址, 幂等, 重试, 限流, 内存口径以本文为准, ADR 讲方向与理由, `docs/providers/qq-napcat.md` 与 `docs/providers/github-app.md` 只描述各自 provider 如何实现本文的契约, 三者与本文冲突时以本文为准
决策记录见 `.agents/notes/implemented/feature/2026-11-02-messaging-router-gateway.md`
平台调研, NapCat 内置引擎与既有 REST 路由仍以 `docs/messaging-plugins.md` 为准, 本文只描述在其之上新增的路由层
凡标注 "需复核" 的数字都不是本项目实测值, 复核方法写在同一处, 实现前必须逐条核对

## 1. 目录与模块划分

分层方向保持 api -> server -> models, 私有实现放 `impl/`, 单个 py 文件不超过 300 行, 每个目录 2 到 5 个 py 文件, `__init__.py` 不计入

现状约束

- `server/src/hx_email/server/messaging/` 已有 engine, onebot, registry, store, types 共 5 个 py 文件, 已满, 路由层不能放进去
- `server/src/hx_email/api/impl/messaging/` 已有 action_routes, event_routes, routes, schemas, serializers 共 5 个 py 文件, 同样已满
- `server/src/hx_email/models/` 已有 5 个迁移文件, 新表与新列的迁移写进现有 `models/messaging.py` 的 `migrate_messaging_schema`, 不新增文件

新增目录与文件

| 路径                                                               | 职责                                                                              | 预计行数 |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------- | -------- |
| `server/src/hx_email/server/router/types.py`                       | envelope, SessionRef, Route, Delivery, Cursor 等数据类与 `MessagingProvider` 协议 | 200      |
| `server/src/hx_email/server/router/facade.py`                      | 路由层唯一公开入口, 被 MCP 与 REST 共同调用                                       | 260      |
| `server/src/hx_email/server/router/registry.py`                    | provider 注册表, 按 platform 字符串查找 provider                                  | 90       |
| `server/src/hx_email/server/router/hub.py`                         | 进程内订阅信号分发, 每订阅者有界队列                                              | 150      |
| `server/src/hx_email/server/router/impl/outbox.py`                 | 出站排队, 令牌桶整形, 退避重试, 风控熔断                                          | 280      |
| `server/src/hx_email/server/router/impl/store.py`                  | router 各表读写, cursor 增量查询, 保留期清理                                      | 290      |
| `server/src/hx_email/server/router/impl/envelope.py`               | envelope 序列化, raw 大字段落盘与回收, cursor 编解码                              | 180      |
| `server/src/hx_email/server/router/providers/qq.py`                | QQ provider, 调用 `OneBotAdapter` 的结构化动作接口并复用事件归一化                | 220      |
| `server/src/hx_email/server/router/providers/github.py`            | GitHub App provider, webhook 解析与评论发送                                       | 280      |
| `server/src/hx_email/server/router/providers/impl/github_auth.py`  | App JWT 签发与 installation token 缓存                                            | 140      |
| `server/src/hx_email/server/router/providers/impl/webhook_sign.py` | 入站 HMAC 校验与出站 webhook 签名                                                 | 80       |
| `server/src/hx_email/api/impl/router/rest_routes.py`               | `/api/v1/router` REST 兼容面                                                      | 280      |
| `server/src/hx_email/api/impl/router/ingress_routes.py`            | 平台回调入口 `/api/v1/router/ingress/...`                                         | 120      |
| `server/src/hx_email/api/impl/router/mcp_server.py`                | MCP tool 与 resource 定义, 挂载到 `/mcp`                                          | 280      |
| `server/src/hx_email/api/impl/router/schemas.py`                   | 共享的 pydantic 入参模型, 同时导出 JSON Schema 给 MCP                             | 200      |

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

## 2. 会话地址语法

source 与 sink 共用同一套地址, 统一叫 session 地址, 这是全套文档唯一的会话标识, 也是写入 `messaging_messages.chat_id` 的值

格式固定为 `<platform>:<instance_id>:<session_type>:<peer>`, 各段用英文冒号分隔, 前三段只含小写字母与数字

| 平台                    | session_type | peer                      | 示例                            |
| ----------------------- | ------------ | ------------------------- | ------------------------------- |
| QQ 好友私聊             | `private`    | 对方 QQ 号                | `qq:3:private:10001`            |
| QQ 群                   | `group`      | 群号                      | `qq:3:group:123456789`          |
| QQ 群临时会话           | `temp`       | `<群号>-<对方 QQ 号>`     | `qq:3:temp:123456789-10001`     |
| QQ 空间说说             | `qzonepost`  | `<主人 QQ 号>_<tid>`      | `qq:3:qzonepost:10001_a8b6...`  |
| GitHub 仓库             | `repo`       | `<owner>/<repo>`          | `github:7:repo:hx/HX-Email`     |
| GitHub issue 或 PR 线程 | `issue`      | `<owner>/<repo>#<number>` | `github:7:issue:hx/HX-Email#42` |

- `instance_id` 就是 `messaging_instances.id`, 一个实例对应一个平台账号 (一个 QQ 号或一个 GitHub App), 地址天然实现会话粘性, 同一个群被两个 QQ 号加入时是两个不同地址
- 不使用平台账号号码 (例如 QQ 的 self_id) 作地址前缀, 因为换号即换实例, 而协议端从 NapCat 换成备用实现时实例行不变, 地址也不变
- QQ 号与群号是两套独立编号, 数值可以相同, 地址第三段把它们分开, 这是修复现有 `impl/events.py` 里 `chat_id = group_id or user_id` 混淆的方式
- `temp` 会话的回复必须同时带群号与对方 QQ 号, 所以 peer 里两者都有
- GitHub 的 issue 与 PR 共用 `#<number>` 编号空间, 同一仓库内不会冲突, 是 issue 还是 PR 记在 `raw.gh_thread_kind`
- 仓库地址只能作为 source (用于前缀订阅与建 issue), 向仓库地址发送等价于建 issue, 需要在 payload 中带 `title`
- route 的 source 选择器允许前缀匹配, 例如 `qq:3:group:` 表示该账号下全部群, `github:7:issue:hx/HX-Email#` 表示该仓库全部线程
- 反向解析规则唯一: 按前三个冒号拆成 4 段, 第 4 段原样作为 peer, 解析失败返回 `session_not_found`
- 现有 `MessagingMessage.chat_type` 列与 `ChatType` 字面量 (`private`, `group`, `channel`) 只为旧前端保留, 路由层不读它; 写入时 `private` 与 `temp` 记为 `private`, `group`, `repo`, `issue` 记为 `group`, 路由层从不产生 `channel`

### 2.5 地址 v2 (契约 v2, 对外首选)

v1 地址把类型放在 peer 前面, 只能表达一层, "某仓库下所有线程" 只能靠字符前缀, QQ 频道 (guild/channel) 与 QQ 空间 (主人/说说/评论) 这类多层对象放不进去, 且平台与类型是核心里写死的枚举. v2 改为由平台声明的层级路径, v1 继续作为存储键与兼容入参

```
address := <platform>:<instance_id>( /<kind>[/<id>] )*
id      := 由该 kind 的 id_parts 个 "/" 分段组成 (GitHub repo 为 2: owner/name)
```

| v2                                      | 含义                                 | 对应 v1                                                       |
| --------------------------------------- | ------------------------------------ | ------------------------------------------------------------- |
| `qq:3`                                  | 账号下全部会话 (选择器)              | `qq:3:`                                                       |
| `qq:3/group`                            | 账号下全部群 (选择器)                | `qq:3:group:`                                                 |
| `qq:3/group/555`                        | 群会话                               | `qq:3:group:555`                                              |
| `qq:3/private/10001`                    | 好友私聊                             | `qq:3:private:10001`                                          |
| `qq:3/temp/555-10001`                   | 群临时会话                           | `qq:3:temp:555-10001`                                         |
| `github:7/repo/hx/HX-Email`             | 仓库本身, 作为选择器时含其下全部线程 | `github:7:repo:hx/HX-Email` 加 `github:7:issue:hx/HX-Email#*` |
| `github:7/repo/hx/HX-Email/issue/42`    | issue 或 PR 线程                     | `github:7:issue:hx/HX-Email#42`                               |
| `qqbot:5/guild/<频道>/channel/<子频道>` | QQ 频道的文字子频道 (官方机器人)     | `qqbot:5:channel:<频道>/<子频道>`                             |
| `qq:3/qzone/10001`                      | 该 QQ 号空间的全部说说 (选择器)      | `qq:3:qzonepost:10001_*`                                      |
| `qq:3/qzone/10001/post/<tid>`           | 一条说说及其评论                     | `qq:3:qzonepost:10001_<tid>`                                  |

- 区分规则: 实例号后紧跟 `/` 或结束为 v2, 紧跟 `:` 为 v1. 所有接受 session, sink, source 的入口两种都收, 以 v1 落库与去重, 所以同一会话用两种写法发送共享幂等键
- 前缀按路径段匹配, 不按字符: `group/12` 不覆盖 `group/123`; 选择器可以停在一个 kind 上 (`qq:3/group`) 表示该 kind 全部对象, 停在一个对象上表示它及其下全部子对象
- kind 的层级, id 段数, 正则, 与 v1 的映射 (`legacy_type`, `legacy_peer` 模板如 `{repo}#{issue}`) 全部写在平台声明里 (`server/contract/builtin.py`), 核心不再枚举平台与类型; 新平台或新层级只加声明与 provider
- 所有返回 session 或 sink 的地方同时返回 `address` (v2); 一个无法映射的 v1 值返回空字符串而不是报错
- `capabilities_list` (MCP) 与 `GET /api/v1/router/capabilities` (REST) 返回每个平台的地址层级, 事件种类, 已支持的信号与可用动作; 只声明已实现的能力; GitHub discussion 与 commit 已于 2026-11-08 加入声明 (只收不发), QQ 空间 (`qzone`, `post`) 于 2026-11-09 加入; QQ 频道是独立平台 `qqbot` (官方机器人, `guild`, `channel`), 同日加入, 见 ADR 0009 与 docs/providers/qq-bot.md
- 风控等级与整形档位按平台声明, 可按 kind 覆盖: 每个地址层级在 capabilities 里带 `risk_level` 与 `rate_profile`. QQ 聊天为 `third_party` / `qq`, QQ 空间为 `unofficial_web` / `qzone`, QQ 频道为 `official` / `qqbot`, GitHub 为 `official` / `github`
- 决策记录: `.agents/notes/implemented/feature/2026-11-08-router-contract-v2.md`, ADR 0006

## 3. 统一 envelope

### 3.1 字段定义

| 字段                  | 类型           | 说明                                                          | 存储位置                                      |
| --------------------- | -------------- | ------------------------------------------------------------- | --------------------------------------------- |
| `id`                  | string         | 网关内全局 ID, 形如 `m_<messaging_messages.id>`               | 主键 `id`                                     |
| `cursor`              | string         | 读到这一条之后的续读位置                                      | 由 `id` 编码                                  |
| `platform`            | string         | `qq` 或 `github`                                              | 由 `chat_id` 第 1 段解析                      |
| `instance_id`         | integer        | 所属账号实例                                                  | 列 `instance_id`                              |
| `session`             | string         | session 地址                                                  | 列 `chat_id`                                  |
| `session_type`        | string         | `private`, `group`, `temp`, `repo`, `issue` 之一              | 由 `chat_id` 第 3 段解析                      |
| `direction`           | string         | `inbound` 或 `outbound`                                       | 列 `direction`                                |
| `sender`              | object         | `{id, name, is_self}`                                         | 列 `sender_id`, `sender_name`, 新列 `is_self` |
| `text`                | string         | 纯文本正文, 富文本段落拍平, 非文本段落写成 `[image]` 这类占位 | 列 `text`                                     |
| `reply_to`            | string         | 被回复消息的 `platform_message_id`, 没有则为空串              | 新列 `reply_to`                               |
| `platform_message_id` | string         | 平台原生消息 ID                                               | 列 `message_id`                               |
| `attachments`         | array          | `{kind, url, name, size}` 列表, 只存引用不存内容              | 新列 `attachments_json`                       |
| `occurred_at`         | string         | 平台侧时间, ISO 8601 UTC, 以 `Z` 结尾                         | 新列 `occurred_at`                            |
| `received_at`         | string         | 网关落库时间, ISO 8601 UTC, 以 `Z` 结尾                       | 列 `created_at`, 序列化时转换格式             |
| `raw`                 | object 或 null | provider 私有原始载荷, 默认不返回, `include_raw=true` 时返回  | 列 `raw_json` 或落盘文件                      |
| `raw_ref`             | string         | raw 超过 16 KB 时落盘的相对路径, 小于阈值时为空串             | 新列 `raw_ref`                                |

- 每个字段都有确定的存储位置, 读取时不需要按 provider 解析 `raw`, 这让 `filter.exclude_self` 与 `reply_to` 能直接走 SQL, 也让 raw 落盘后 envelope 仍然完整
- 现有 `created_at` 列由 SQLite `datetime('now')` 生成, 格式为 `YYYY-MM-DD HH:MM:SS` 且为 UTC, 序列化时补成 `YYYY-MM-DDTHH:MM:SSZ`
- 16 KB 是本项目自定的阈值, 不是外部数字

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
  "sender": { "id": "10001", "name": "alice", "is_self": false },
  "text": "今晚的发布推迟到 9 点",
  "reply_to": "",
  "platform_message_id": "1873992211",
  "attachments": [],
  "occurred_at": "2026-11-02T15:20:05Z",
  "received_at": "2026-11-02T15:20:06Z",
  "raw": null,
  "raw_ref": ""
}
```

### 3.3 QQ 映射 (OneBot 11 消息事件)

| OneBot 字段                                                       | envelope 字段                                                                                                         |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `message_type="group"`, `group_id`                                | `session_type="group"`, `session="qq:<iid>:group:<group_id>"`                                                         |
| `message_type="private"`, `sub_type="friend"`, `user_id`          | `session_type="private"`, `session="qq:<iid>:private:<user_id>"`                                                      |
| `message_type="private"`, `sub_type="group"`, 来源群号, `user_id` | `session_type="temp"`, `session="qq:<iid>:temp:<group_id>-<user_id>"`, 来源群号的字段位置需复核, 见 qq-napcat 第 4 节 |
| `user_id`, `sender.nickname`                                      | `sender.id`, `sender.name`                                                                                            |
| `self_id == user_id`                                              | `sender.is_self=true`                                                                                                 |
| `message` 段落数组                                                | `text` 由现有 `_segments_text` 逻辑拍平, `image` 段落进入 `attachments`                                               |
| `message` 中的 `reply` 段落                                       | `reply_to`                                                                                                            |
| `message_id`                                                      | `platform_message_id`                                                                                                 |
| `time` (Unix 秒)                                                  | `occurred_at`                                                                                                         |
| `message_id` 与 `time`                                            | 入站去重键 `dedup_key="qq:<message_id>:<time>"`, 见第 7 节                                                            |

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
    "sender": { "nickname": "alice" },
    "message": [{ "type": "text", "data": { "text": "今晚的发布推迟到 9 点" } }]
  },
  "session": "qq:3:group:123456789",
  "sender": { "id": "10001", "name": "alice", "is_self": false },
  "platform_message_id": "1873992211",
  "occurred_at": "2026-11-02T15:20:05Z"
}
```

### 3.4 GitHub 映射

订阅的事件集合以本节为准, ADR 与 github-app 文档与之一致

| 事件 (X-GitHub-Event)                       | action                             | 产出                                              | session                                                | platform_message_id 与 dedup_key                    |
| ------------------------------------------- | ---------------------------------- | ------------------------------------------------- | ------------------------------------------------------ | --------------------------------------------------- |
| `issue_comment`                             | created, edited                    | 一条消息, edited 只覆盖同 dedup_key 记录的 `text` | `github:<iid>:issue:<full_name>#<issue.number>`        | `ic:<comment.id>`                                   |
| `pull_request_review_comment`               | created, edited                    | 同上, `reply_to` 取 `rc:<in_reply_to_id>`         | `github:<iid>:issue:<full_name>#<pull_request.number>` | `rc:<comment.id>`                                   |
| `pull_request_review`                       | submitted                          | 一条消息, `text` 为结论加正文                     | 同上                                                   | `rv:<review.id>`                                    |
| `issues`                                    | opened                             | 一条消息, `text` 为标题加空行加正文               | `github:<iid>:issue:<full_name>#<issue.number>`        | `is:<issue.id>`                                     |
| `issues`                                    | closed, reopened                   | 一条状态消息, `text` 用固定模板                   | 同上                                                   | `is:<issue.id>:<action>:<X-GitHub-Delivery>`        |
| `pull_request`                              | opened                             | 一条消息, `text` 为标题加空行加正文               | `github:<iid>:issue:<full_name>#<number>`              | `pr:<pull_request.id>`                              |
| `pull_request`                              | closed, reopened, ready_for_review | 一条状态消息                                      | 同上                                                   | `pr:<pull_request.id>:<action>:<X-GitHub-Delivery>` |
| `installation`, `installation_repositories` | 全部                               | 不产出消息, 只更新 installation 与仓库映射        | 无                                                     | 无                                                  |

| GitHub 字段                                                                  | envelope 字段                                             |
| ---------------------------------------------------------------------------- | --------------------------------------------------------- |
| 评论或 review 的 `user.login`, `user.id`                                     | `sender.name`, `sender.id`                                |
| `performed_via_github_app.id == 本 App` 或 `user.login == "<app-slug>[bot]"` | `sender.is_self=true`                                     |
| `comment.body`                                                               | `text`, 去掉末尾的 `<!-- hx-router delivery=... -->` 标记 |
| `comment.created_at` 等 GitHub 给出的时间                                    | `occurred_at`, 原样保留 GitHub 的 `Z` 结尾 UTC 字符串     |
| 请求头 `X-GitHub-Delivery`                                                   | 写入 `raw.gh_delivery`, 并进入 ingress 去重表, 见第 7 节  |

```json
{
  "platform": "github",
  "instance_id": 7,
  "session": "github:7:issue:hx/HX-Email#42",
  "session_type": "issue",
  "sender": { "id": "583231", "name": "octocat", "is_self": false },
  "text": "复现了, 附上日志",
  "platform_message_id": "ic:2449601123",
  "occurred_at": "2026-11-02T13:31:00Z",
  "raw": {
    "gh_event": "issue_comment",
    "gh_action": "created",
    "gh_delivery": "72d3162e-cc78-11e3-81ab-4c9367dc0958"
  }
}
```

- 未列出的事件与 action 返回 2xx 后丢弃, 不入库
- `push` 事件不订阅, 因此不申请 Contents 权限

### 3.5 Event v2 视图

`messages_pull`, `events_wait`, `GET /router/messages`, `GET /router/wait` 与 SSE 返回的每一项, 在 3.1 的全部字段之外增加以下字段, 3.1 字段保持不变

| 字段       | 类型   | 说明                                                                                                                                                                                                                                                |
| ---------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `contract` | int    | 固定为 2                                                                                                                                                                                                                                            |
| `address`  | string | 所属会话的 v2 地址                                                                                                                                                                                                                                  |
| `thread`   | string | 会话线程地址; 当前两个平台与 `address` 相同, QQ 空间评论与 GitHub review 线程接入后会指向更细的线程                                                                                                                                                 |
| `parent`   | string | 上一层地址, issue 的上一层是仓库, QQ 会话的上一层是账号                                                                                                                                                                                             |
| `kind`     | string | 事件种类, 取自平台声明: QQ 聊天为 `message`, QQ 空间为 `post`, `comment` (取值见 docs/providers/qq-zone.md 3); GitHub 为 `thread_opened`, `thread_state`, `comment`, `review_comment`, `review`, `commit` (取值见 docs/providers/github-app.md 3.5) |
| `mentions` | array  | `[{id, name, is_self}]`, 平台未提供时为空数组                                                                                                                                                                                                       |
| `flags`    | object | `from_self`, `mention_self`, `reply_to_self`; 值为 `null` 表示该平台尚未上报此信号 (见 capabilities 的 `signals`), 与 `false` 含义不同                                                                                                              |
| `segments` | array  | 有序内容段, 当前由 `reply_to`, `text`, `attachments` 派生: `{type: "reply", id}`, `{type: "text", text}`, 附件段沿用附件字段                                                                                                                        |

- provider 在 envelope dict 里给出 `mentions`, `flags`, `segments` 时以 provider 为准, 否则按上表派生
- provider 给出的 `kind`, `mentions`, `flags` 随行存进 `messaging_messages.trigger_json` (2026-11-08 起, GitHub 先行); 视图优先用存下的值, 旧行与未上报的平台才按 `platform_message_id` 前缀与发送者推导, 推导不出的信号为 `null`
- 带 `reply_to` 且 provider 上报了触发字段的消息, 入库时按 `reply_to` 查同实例的上一条, 它是本账号发出的就把 `reply_to_self` 置 true

## 4. 数据模型增量

迁移全部写进现有 `server/src/hx_email/models/messaging.py` 的 `migrate_messaging_schema`; SQLite 的 `ALTER TABLE ... ADD COLUMN` 没有 `IF NOT EXISTS`, 迁移先读 `PRAGMA table_info(messaging_messages)` 再只补缺的列

```sql
ALTER TABLE messaging_messages ADD COLUMN is_self INTEGER NOT NULL DEFAULT 0;
ALTER TABLE messaging_messages ADD COLUMN reply_to TEXT NOT NULL DEFAULT '';
ALTER TABLE messaging_messages ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE messaging_messages ADD COLUMN occurred_at TEXT NOT NULL DEFAULT '';
ALTER TABLE messaging_messages ADD COLUMN raw_ref TEXT NOT NULL DEFAULT '';
ALTER TABLE messaging_messages ADD COLUMN dedup_key TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_messaging_messages_dedup
ON messaging_messages(instance_id, dedup_key) WHERE dedup_key <> '';

CREATE INDEX IF NOT EXISTS idx_messaging_messages_created
ON messaging_messages(created_at);

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
  user_id INTEGER NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL,
  instance_id INTEGER REFERENCES messaging_instances(id),
  route_id INTEGER REFERENCES router_routes(id),
  session TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL DEFAULT (datetime('now')),
  give_up_at TEXT NOT NULL,
  platform_message_id TEXT NOT NULL DEFAULT '',
  last_error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  CHECK (
    (kind = 'send' AND instance_id IS NOT NULL AND route_id IS NULL AND session <> '')
    OR (kind = 'webhook' AND route_id IS NOT NULL AND instance_id IS NULL)
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_router_outbox_send
ON router_outbox(instance_id, idempotency_key) WHERE kind = 'send';

CREATE UNIQUE INDEX IF NOT EXISTS uq_router_outbox_webhook
ON router_outbox(route_id, idempotency_key) WHERE kind = 'webhook';

CREATE INDEX IF NOT EXISTS idx_router_outbox_due
ON router_outbox(status, next_attempt_at);

CREATE TABLE IF NOT EXISTS router_ingress_deliveries (
  instance_id INTEGER NOT NULL REFERENCES messaging_instances(id),
  delivery_id TEXT NOT NULL,
  event TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  payload_encrypted TEXT NOT NULL DEFAULT '',
  received_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (instance_id, delivery_id)
);

CREATE TABLE IF NOT EXISTS router_api_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  key_prefix TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_used_at TEXT,
  revoked_at TEXT
);
```

- 新列全部带默认值, 旧行不需要回填; 旧行的 `dedup_key` 为空串, 不受唯一索引约束, 因此建索引前不需要清理已有重复行
- `router_outbox.kind` 为 `send` 或 `webhook`: `send` 是平台出站, 属于一个账号实例与一个 session; `webhook` 是向外部 URL 投递 envelope, 属于一条 route, route 的 source 前缀可以跨实例 (例如 `qq:`), 因此 webhook 行不带 `instance_id`, 由 CHECK 约束保证两类行各自的必填列
- `router_outbox.user_id` 让两类行都能按用户隔离与清理
- `router_outbox.status` 取值 `queued`, `sending`, `sent`, `unknown`, `failed`, `dead`, `held`, 含义见第 7 节与第 9 节
- `router_routes.delivery` 取值 `mcp`, `sse`, `webhook`, `poll`, 含义见第 5.7 节
- `router_routes.status` 取值 `active`, `paused_backlog`, `expired`
- `router_ingress_deliveries` 只给 GitHub 这类带投递 ID 的平台用, `status` 取 `pending`, `done`, `ignored`, 进程重启时重新处理 `pending` 行
- `router_api_keys` 见第 8.2 节

## 5. MCP tool 清单

MCP server 名为 `hx-router`, 传输为 streamable HTTP (`/mcp`) 与 stdio (`hx-email mcp`), 每个调用都以路由 API Key 绑定到一个用户
所有 tool 失败时返回 MCP 标准 `isError=true`, 内容中带 `{code, message, retryable}`, `code` 取值见第 9 节

### 5.1 `sources_list`

列出当前用户可用的平台, 账号实例及其在线与出站状态

```json
{
  "type": "object",
  "properties": {
    "platform": {
      "type": "string",
      "enum": ["qq", "github"],
      "description": "只看某个平台"
    }
  },
  "additionalProperties": false
}
```

返回 `{"sources": [{"platform": "qq", "instance_id": 3, "name": "运维小号", "state": "online", "account_id": "20002", "outbound": "open", "held_until": "", "risk_level": "third_party"}]}`

- `state` 取现有 `AdapterState` 的 `stopped`, `connecting`, `online`, `error`
- `outbound` 取 `open` (正常出站), `held` (自动熔断中, `held_until` 给出自动恢复时间), `manual_hold` (自动熔断当天第三次触发, 或用户在前端手动暂停, 只能由用户调用第 6 节的 resume 接口解除, `held_until` 为空串)

### 5.2 `sessions_list`

列出某个账号实例下可以监听与发送的会话

```json
{
  "type": "object",
  "properties": {
    "instance_id": { "type": "integer" },
    "session_type": {
      "type": "string",
      "enum": ["private", "group", "temp", "repo", "issue"]
    },
    "query": { "type": "string", "description": "按名称模糊过滤" },
    "limit": { "type": "integer", "minimum": 1, "maximum": 200, "default": 50 }
  },
  "required": ["instance_id"],
  "additionalProperties": false
}
```

返回 `{"sessions": [{"session": "qq:3:group:123456789", "session_type": "group", "title": "发布群", "last_cursor": "c1.3.10452"}]}`

### 5.3 `session_select`

选定一个会话并返回它的元数据, 当前游标与限流参数, 作为后续 pull 与 subscribe 的起点; 服务端不保存 "选定" 状态, 返回的 cursor 由调用方保存

```json
{
  "type": "object",
  "properties": {
    "session": { "type": "string", "description": "session 地址" },
    "from": { "type": "string", "enum": ["now", "earliest"], "default": "now" }
  },
  "required": ["session"],
  "additionalProperties": false
}
```

返回 `{"session": "qq:3:group:123456789", "title": "发布群", "can_send": true, "cursor": "c1.3.10452", "limits": {"per_session_interval_seconds": 3.0, "per_account_per_minute": 20, "max_text_length": 1500}}`, `from="now"` 时 cursor 指向最新一条之后, `from="earliest"` 时为 `c1.<iid>.0`

### 5.4 `messages_pull`

按 cursor 读取一个会话或一个前缀下的增量消息, 同步, 只读数据库

```json
{
  "type": "object",
  "properties": {
    "source": { "type": "string", "description": "session 地址或地址前缀" },
    "cursor": {
      "type": "string",
      "description": "session_select 或上次 messages_pull 返回的 cursor"
    },
    "limit": { "type": "integer", "minimum": 1, "maximum": 200, "default": 50 },
    "direction": {
      "type": "string",
      "enum": ["inbound", "outbound", "both"],
      "default": "inbound"
    },
    "include_raw": { "type": "boolean", "default": false }
  },
  "required": ["source", "cursor"],
  "additionalProperties": false
}
```

返回 `{"messages": [<envelope>], "next_cursor": "c1.3.10460", "has_more": false}`, 消息按 cursor 升序; cursor 必填, 服务端不保存调用方的读位置, 没有 cursor 的调用方先调 `session_select`

### 5.5 `message_send`

向一个 sink 发送消息, 写入 outbox, 在整形器允许时同步投递并等待结果

```json
{
  "type": "object",
  "properties": {
    "sink": { "type": "string", "description": "session 地址" },
    "text": { "type": "string", "minLength": 1, "maxLength": 4000 },
    "title": {
      "type": "string",
      "description": "只在向 GitHub 仓库地址建 issue 时必填"
    },
    "reply_to": { "type": "string", "default": "" },
    "idempotency_key": {
      "type": "string",
      "minLength": 8,
      "maxLength": 64,
      "pattern": "^[A-Za-z0-9_.:-]+$"
    },
    "wait_seconds": {
      "type": "number",
      "minimum": 0,
      "maximum": 5,
      "default": 5
    }
  },
  "required": ["sink", "text", "idempotency_key"],
  "additionalProperties": false
}
```

返回 `{"delivery_id": "d_881", "status": "sent", "deduplicated": false, "platform_message_id": "1873992260", "queued_until": ""}`

- 被整形推迟时 `status="queued"` 且 `queued_until` 给出预计投递时间
- `idempotency_key` 由调用方生成, 推荐 UUID v4 但不强制, 语义见第 7.2 节; 命中已有记录时返回首次的 `delivery_id` 与当前状态, 并带 `deduplicated=true`
- `text` 的 4000 是跨平台入参上限; 各平台单条上限以 `session_select` 返回的 `max_text_length` 为准, QQ 为 1500, 超过时返回 `text_too_long`, 路由层不拆条

### 5.6 `delivery_status`

查询一次发送或一次 webhook 投递的状态, 支持按 `delivery_id` 查或按 `idempotency_key` 加 `sink` 查

```json
{
  "type": "object",
  "properties": {
    "delivery_id": { "type": "string" },
    "idempotency_key": { "type": "string" },
    "sink": { "type": "string" }
  },
  "oneOf": [
    { "required": ["delivery_id"] },
    { "required": ["idempotency_key", "sink"] }
  ],
  "additionalProperties": false
}
```

返回 `{"delivery_id": "d_881", "kind": "send", "status": "sent", "attempts": 1, "platform_message_id": "1873992260", "last_error": "", "updated_at": "2026-11-02T13:21:00Z"}`

- 按 `idempotency_key` 查只适用于 `kind=send`, `sink` 用于定位实例, 对应唯一索引 `(instance_id, idempotency_key)`

### 5.7 `route_subscribe`

创建一条订阅规则, 让某个 source 前缀的新消息交给当前 MCP 会话, SSE 连接, 外部 webhook, 或留给消费者自己长轮询

```json
{
  "type": "object",
  "properties": {
    "source": { "type": "string", "description": "session 地址或前缀" },
    "delivery": {
      "type": "string",
      "enum": ["mcp", "sse", "webhook", "poll"],
      "default": "mcp"
    },
    "webhook_url": { "type": "string", "format": "uri" },
    "filter": {
      "type": "object",
      "properties": {
        "sender_ids": { "type": "array", "items": { "type": "string" } },
        "keywords": { "type": "array", "items": { "type": "string" } },
        "exclude_self": { "type": "boolean", "default": true }
      },
      "additionalProperties": false
    },
    "from_cursor": { "type": "string" },
    "ttl_seconds": { "type": "integer", "minimum": 60, "maximum": 2592000 }
  },
  "required": ["source"],
  "additionalProperties": false
}
```

返回 `{"route_id": "r_12", "resource_uri": "hx-router://routes/r_12", "cursor": "c1.3.10452", "webhook_secret": "只在 delivery=webhook 时返回一次"}`

四种 delivery 的定义

- `mcp`: 服务端自动对 `resource_uri` 执行 `resources/subscribe`, 有新数据时发 `notifications/resources/updated`, 客户端再读 resource 或调用 `messages_pull`
- `sse`: 消费者连接 `GET /api/v1/router/routes/{route_id}/stream`, 服务端按帧推送 envelope
- `webhook`: 服务端经 outbox 向 `webhook_url` 投递 envelope 批次, `webhook_url` 必填, 重试规则见第 7.4 节
- `poll`: 服务端不主动推送任何东西, 消费者用 `events_wait` 或 `GET /routes/{route_id}/wait` 长轮询, 用 `route_ack` 推进位置, 给不支持 resource 订阅也不便保持 SSE 的客户端使用

### 5.8 `route_unsubscribe`

删除一条订阅规则并释放它的信号队列

```json
{
  "type": "object",
  "properties": { "route_id": { "type": "string" } },
  "required": ["route_id"],
  "additionalProperties": false
}
```

返回 `{"route_id": "r_12", "removed": true}`

### 5.9 `routes_list`

列出当前用户的订阅规则及其积压情况

```json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": ["active", "paused_backlog", "expired", "all"],
      "default": "active"
    }
  },
  "additionalProperties": false
}
```

返回 `{"routes": [{"route_id": "r_12", "source": "qq:3:group:", "delivery": "mcp", "status": "active", "ack_cursor": "c1.0.10452", "backlog": 0, "expires_at": ""}]}`

### 5.10 `events_wait`

长轮询, 阻塞到某条订阅有新数据或超时, 适用于任何 delivery 的 route, 是 `poll` 类 route 的唯一读取方式之一

```json
{
  "type": "object",
  "properties": {
    "route_id": { "type": "string" },
    "cursor": { "type": "string" },
    "timeout_seconds": {
      "type": "integer",
      "minimum": 1,
      "maximum": 55,
      "default": 25
    },
    "limit": { "type": "integer", "minimum": 1, "maximum": 50, "default": 20 }
  },
  "required": ["route_id", "cursor"],
  "additionalProperties": false
}
```

返回 `{"messages": [<envelope>], "next_cursor": "c1.0.10461", "gap": false, "timed_out": false}`, 等待期间不占用线程, 由 `hub.py` 的 asyncio 条件变量唤醒, 不使用定时器

### 5.11 `route_ack`

确认某条订阅已经处理到某个 cursor, 服务重启后按此续推

```json
{
  "type": "object",
  "properties": {
    "route_id": { "type": "string" },
    "cursor": { "type": "string" }
  },
  "required": ["route_id", "cursor"],
  "additionalProperties": false
}
```

返回 `{"route_id": "r_12", "ack_cursor": "c1.0.10461"}`

### 5.12 MCP resource

- `hx-router://routes/{route_id}` 读取返回该 route 自 `ack_cursor` 之后的至多 50 条 envelope
- 有新数据时服务端发 `notifications/resources/updated`, 客户端再调用 `resources/read` 或 `messages_pull`
- 通知是提示不是数据, 丢失通知不会丢数据

### 5.13 阶段 2 已落地的订阅接口

5.7 到 5.11 是最初的设计稿. 阶段 2 实际落地的形态如下, 以本节为准:

- 名称: 对外叫 subscription, MCP 工具为 `subscriptions_list`, `subscription_create`, `subscription_wait`, `subscription_ack`; 原有 `events_wait` 保留, 仍按 source 加 cursor 等待. 存储表仍是 `router_routes`, 新增 `name`, `updated_at` 两列与 `(user_id, id)` 索引, 每个账号最多 50 条.
- id 是整数, 不再加 `r_` 前缀; `source` 接受 v1 前缀与契约 v2 地址或选择器 (见 2.5), 返回同时带 `source` 与 `address`.
- `filter` 只有 `direction`, `kinds`, `exclude_self` (默认 true), `mention_self`, `contains` 五个键, 作用在 3.5 的 Event v2 视图上; 未知键报 `route_invalid`.
- `from` 为 `now` (默认, ack 停在当前最新一条) 或 `earliest`.
- `delivery` 在阶段 2 只有 `pull` (阶段 3 增加 `webhook`, 见 5.14): 消费者用 `/subscriptions/{id}/events` 长轮询或 `/subscriptions/{id}/stream` 收 SSE, 用 `/ack` 推进. 长轮询不推进 ack, 处理完再确认, 得到至少一次语义; SSE 的 `auto_ack=true` 在每批推出后确认, 适合看板这类不在乎重放的消费者. webhook 与 WebSocket 在阶段 3, MCP resource 通知在阶段 7.
- 暂停的订阅 `/events` 立即返回 `paused: true`, `/stream` 返回 `route_invalid`.
- 积压 `backlog` 是 ack 之后范围内未过滤的条数, 超过 999 时封顶并带 `backlog_capped: true`.
- 错误码新增 `route_not_found` (404), `route_invalid` (422), `route_limit` (409).

等待的实现 (`server/hub/`):

- `bus.py`: 每个等待者按自己的 source 与可读实例注册一个匹配器; 每次落库 (入站与出站记录) 调 `BUS.publish([Hit(instance_id, chat_id, direction)])`, 只唤醒命中的等待者. 原来进程内唯一的 `threading.Condition` 与版本号已删除, 不再一条消息唤醒所有人. 匹配器只会多匹配不会漏匹配, 被误唤醒的等待者按 cursor 重读一次再睡.
- `consume.py`: `/wait`, `/stream`, `/subscriptions/{id}/events`, `/subscriptions/{id}/stream`, MCP 的 `events_wait` 与 `subscription_wait` 都是协程, 先注册等待者再读库 (读库借一次工作线程, 毫秒级), 然后在 `asyncio.Event` 上睡, 等待期间不占线程池. 跨线程唤醒用 `loop.call_soon_threadsafe`.
- 被过滤掉的整页不会触发睡眠: 游标前移后立即读下一页, 直到有符合条件的消息, 没有更多, 或超时.

### 5.14 阶段 3 已落地的推送通道

以本节为准, 覆盖 5.7 中 `mcp`, `sse`, `webhook`, `poll` 四种 delivery 的设计稿.

- `delivery` 只有两种: `pull` 与 `webhook`. `pull` 订阅用长轮询 (`/events`), SSE (`/stream`) 或 WebSocket (`/ws`) 消费; `webhook` 订阅由服务端推送, 同样可以再开 SSE 或 WebSocket 旁观 (不开 `auto_ack` 时不影响 ack).
- 创建或 `PATCH` 为 `webhook` 时必须给 `webhook_url` (http 或 https, 不含用户名密码, 最长 500); 返回里带一次 `webhook_secret` (`whsec_` 开头), 之后只能 `/webhook/rotate` 换新的. URL 与密钥加密存入 `target_encrypted`; 订阅对象里的 `webhook` 字段只给 `url` 与 `push_cursor`.
- 新列 `push_cursor`: 已排成批次的位置. 推送线程为每条活跃 webhook 订阅按其范围注册一个 hub 等待者, 命中后从 `push_cursor` 读, 过滤后每 50 条一批写入 `router_outbox` (`kind='webhook'`, 幂等键 `m_<首>-m_<尾>`).
- 请求: `POST <webhook_url>`, body `{"type": "messages", "subscription_id", "messages": [<Event v2 视图>], "next_cursor", "gap"}`; 头 `X-HX-Router-Signature: sha256=<hex>` (以 `webhook_secret` 对原始 body 做 HMAC-SHA256), `X-HX-Router-Delivery: d_<id>`, `X-HX-Router-Subscription: <id>`. `/webhook/ping` 发 `{"type": "ping", "subscription_id"}`, 签名方式相同, `X-HX-Router-Delivery` 为 `ping`.
- 结果: 2xx 置 `sent`, ack 推到该批 `next_cursor`; 其它状态码, 超时, 连接失败按 7.4 退避 (10 秒起翻倍, 上限 1 小时, 正负 20% 抖动), 到 `give_up_at` 置 `dead`; 订阅暂停时到点批次置 `held`, 恢复后重新排队; `dead` 或 `failed` 批次可经 `/redeliver` 以新的 24 小时窗口重投. 同一订阅一次只有一批在途; 投递在 4 线程小池里进行, 不阻塞平台出站.
- WebSocket `/subscriptions/{id}/ws`: 鉴权取 `Authorization` 头, 或子协议 `bearer.<token>` (浏览器用), 同时请求 `hx-router` 子协议. 服务端帧: `{"type": "ready", "subscription_id", "cursor", "ack_cursor"}`, `{"type": "messages", "messages", "next_cursor"}`, 空闲 25 秒一次 `{"type": "heartbeat", "next_cursor"}`, `{"type": "acked", "ack_cursor"}`, `{"type": "pong"}`, `{"type": "error", "code", "message"}`. 客户端帧: `{"type": "ack", "cursor"}`, `{"type": "ping"}`. 关闭码: 4401 未授权, 4404 订阅不存在, 4409 已暂停.
- MCP `subscription_create` 增加 `delivery` 与 `webhook_url` 参数.
- 为了守住 300 行上限, `server/router/envelope.py` 拆成包 `envelope/` (`session`, `model`, `raw`), `server/router/impl/reader.py` 拆成包 `impl/reader/` (`source`, `rows`, `page`); 两个包重新导出全部旧名字.

## 6. REST 兼容面

前缀 `/api/v1/router`, 鉴权统一为 `Authorization: Bearer <路由 API Key>`, 前端会话 token 同样被接受; 平台回调入口与 API Key 管理接口例外

| 方法   | 路径                                           | 入参                                                                        | 返回                                                                     | 鉴权                                             | 对应 MCP tool                       |
| ------ | ---------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------ | ----------------------------------- |
| GET    | `/sources`                                     | query `platform`                                                            | 同 `sources_list`                                                        | API Key                                          | `sources_list`                      |
| GET    | `/instances/{instance_id}/sessions`            | query `session_type`, `query`, `limit`                                      | 同 `sessions_list`                                                       | API Key                                          | `sessions_list`                     |
| POST   | `/sessions/select`                             | body 同 `session_select`                                                    | 同 `session_select`                                                      | API Key                                          | `session_select`                    |
| GET    | `/messages`                                    | query `source`, `cursor`, `limit`, `direction`, `include_raw`               | 同 `messages_pull`                                                       | API Key                                          | `messages_pull`                     |
| POST   | `/messages`                                    | body 同 `message_send`, 也可用 `Idempotency-Key` 头代替 `idempotency_key`   | 同 `message_send`, 排队时 HTTP 202                                       | API Key                                          | `message_send`                      |
| GET    | `/deliveries/{delivery_id}`                    | 无                                                                          | 同 `delivery_status`                                                     | API Key                                          | `delivery_status` 按 delivery_id 查 |
| GET    | `/deliveries`                                  | query `idempotency_key`, `sink`, 两者必填                                   | 同 `delivery_status`, 无记录时 404                                       | API Key                                          | `delivery_status` 按幂等键查        |
| POST   | `/subscriptions`                               | body `{source, name, filter, from, delivery, webhook_url}`                  | 订阅对象, 含 `ack_cursor`, HTTP 201                                      | API Key                                          | `subscription_create`               |
| GET    | `/subscriptions`                               | 无                                                                          | `{subscriptions: [... backlog], limit}`                                  | API Key                                          | `subscriptions_list`                |
| GET    | `/subscriptions/{id}`                          | 无                                                                          | 订阅对象                                                                 | API Key                                          | 无                                  |
| PATCH  | `/subscriptions/{id}`                          | body `{name?, status?, filter?, delivery?, webhook_url?}`                   | 订阅对象                                                                 | API Key                                          | 无                                  |
| DELETE | `/subscriptions/{id}`                          | 无                                                                          | `{id, deleted: true}`                                                    | API Key                                          | 无                                  |
| GET    | `/subscriptions/{id}/events`                   | query `cursor`, `timeout_seconds` (0 到 55), `limit`                        | 同 `events_wait`, 另带 `subscription_id`, `ack_cursor`                   | API Key                                          | `subscription_wait`                 |
| POST   | `/subscriptions/{id}/ack`                      | body `{cursor}`                                                             | 订阅对象, 只前进不回退                                                   | API Key                                          | `subscription_ack`                  |
| GET    | `/subscriptions/{id}/stream`                   | query `auto_ack`, `cursor`; 头 `Last-Event-ID`                              | `text/event-stream`, 首帧 `event: ready`, 每帧 `id` 为 cursor            | API Key                                          | 无                                  |
| GET    | `/subscriptions/{id}/ws`                       | WebSocket; query `cursor`, `auto_ack`; 子协议 `hx-router`, `bearer.<token>` | 帧 `ready`, `messages`, `heartbeat`, `acked`; 收 `ack`, `ping`           | API Key 或会话 (头或子协议)                      | 无                                  |
| GET    | `/subscriptions/{id}/deliveries`               | query `limit`                                                               | `{subscription_id, deliveries: [...]}`                                   | API Key                                          | 无                                  |
| POST   | `/subscriptions/{id}/deliveries/{d}/redeliver` | 无                                                                          | `{delivery_id, status: queued}`, 只接受 dead 或 failed                   | API Key                                          | 无                                  |
| POST   | `/subscriptions/{id}/webhook/ping`             | 无                                                                          | `{ok, status_code, error, elapsed_ms}`                                   | API Key                                          | 无                                  |
| POST   | `/subscriptions/{id}/webhook/rotate`           | 无                                                                          | 订阅对象, 带一次性 `webhook_secret`                                      | API Key                                          | 无                                  |
| GET    | `/wait`                                        | query `source`, `cursor`, `timeout_seconds`, `limit`, `direction`           | 同 `events_wait`                                                         | API Key                                          | `events_wait`                       |
| GET    | `/stream`                                      | query `source`, `cursor`, `direction`; 头 `Last-Event-ID`                   | `text/event-stream`                                                      | API Key                                          | 无                                  |
| GET    | `/hub`                                         | 无                                                                          | `{waiting, published, webhook_subscriptions}`                            | API Key                                          | 无                                  |
| POST   | `/instances/{instance_id}/outbound/hold`       | 无                                                                          | `{outbound: "manual_hold"}`                                              | 前端会话                                         | 无                                  |
| POST   | `/instances/{instance_id}/outbound/resume`     | 无                                                                          | `{outbound: "open"}`                                                     | 前端会话                                         | 无                                  |
| POST   | `/api-keys`                                    | body `{name}`                                                               | `{id, name, key, key_prefix, created_at}`, `key` 只返回这一次, HTTP 201  | 前端会话                                         | 无                                  |
| GET    | `/api-keys`                                    | 无                                                                          | `{keys: [{id, name, key_prefix, created_at, last_used_at, revoked_at}]}` | 前端会话                                         | 无                                  |
| DELETE | `/api-keys/{id}`                               | 无                                                                          | `{id, revoked: true}`                                                    | 前端会话                                         | 无                                  |
| POST   | `/ingress/qq/{instance_id}`                    | OneBot 11 事件                                                              | `{stored}`                                                               | `X-Messaging-Token`, NapCat 实际携带的头名需复核 | 无                                  |
| POST   | `/ingress/github/{instance_id}`                | GitHub webhook                                                              | 见 github-app 第 5.4 节                                                  | `X-Hub-Signature-256`                            | 无                                  |

- outbound hold 与 resume 以及 API Key 管理只接受前端会话 token, 不接受路由 API Key, 防止一把泄漏的 Key 自己解除熔断或签发新 Key
- 现有 `POST /api/v1/messaging/events/{kind}` 保留, 内部改为转发到同一套 ingress 处理, NapCat 配置不需要立即变更
- 现有 `POST /api/v1/messaging/instances/{id}/send` 保留给前端, 内部改为调用 `facade.send`, 由服务端生成 `idempotency_key`, 共享整形与幂等
- SSE 每 25 秒发送一次注释心跳 `:`, 只在有活跃 SSE 连接时存在, 无连接时没有任何定时器, 这一心跳计入 ADR 0005 的验收项 A2 的允许量

出站 webhook 投递格式

- `POST <webhook_url>`, body 为 `{"route_id", "messages": [<envelope>], "next_cursor"}`, 每批至多 50 条
- 头 `X-HX-Router-Signature: sha256=<hex>`, 以 route 创建时返回的 `webhook_secret` 做 HMAC-SHA256
- 头 `X-HX-Router-Delivery: <delivery_id>`, 接收方据此去重
- 接收方返回 2xx 视为成功并推进该 route 的 `ack_cursor`

## 7. cursor, 去重, 幂等与重试

### 7.1 cursor 与一致性边界

- cursor 格式为 `c1.<instance_id>.<messaging_messages.id>`, 跨实例前缀订阅使用 `c1.0.<id>` 表示全局位置, 对调用方保持不透明
- `messaging_messages.id` 是 SQLite 自增主键, 只在单写者单实例部署下保证单调, 这与 ADR 0002 的部署形态一致
- 读取语义为 `WHERE id > <cursor_id> ORDER BY id ASC LIMIT n`, 单会话读取走 `(instance_id, chat_id, id)` 索引
- 投递语义为至少一次, MCP 通知, SSE, webhook 都可能重复, 消费者以 envelope 的 `id` 去重
- 重启续读: route 的 `ack_cursor` 持久化在 `router_routes`, 进程启动后 SSE 与 webhook 从 `ack_cursor` 续推, MCP 客户端重连后用自己保存的 cursor 调 `messages_pull`
- 一致性边界: 同一 session 内按 id 有序, 跨 session 只保证每条最终可读, 不保证全局因果序
- cursor 指向已被保留期清理删除的位置时, 读取从现存最小 id 开始, 并在返回中带 `gap=true`

### 7.2 出站幂等

- 字段名统一为 `idempotency_key`, 8 到 64 个字符, 由调用方生成, 推荐 UUID v4
- 平台出站 (`kind=send`) 的唯一键为 `(instance_id, idempotency_key)`, 实例由 `sink` 地址第 2 段确定
- webhook 投递 (`kind=webhook`) 的唯一键为 `(route_id, idempotency_key)`, 这类键由服务端生成, 取值为批次首尾 envelope id, 形如 `m_10452-m_10460`
- 幂等窗口等于 outbox 行的保留期, 终态行 (`sent`, `unknown`, `failed`, `dead`) 保留 7 天, 7 天内同键重复调用返回首次的 `delivery_id` 与当前状态并带 `deduplicated=true`, 不新建投递, 也没有单独的 `duplicate` 状态
- 平台侧幂等键: QQ (OneBot 11) 没有; GitHub REST 写接口也没有, GitHub provider 用评论正文末尾的隐藏标记 `<!-- hx-router delivery=<delivery_id> -->` 在结果未知时按标记查重, 这是模拟出来的幂等, 不是平台保证

### 7.3 结果未知与重启语义

- 平台调用超时, 或进程在调用期间退出, 都属于结果未知: 平台可能已经收到
- 结果未知的 `kind=send` 行一律置为 `unknown`, 不自动重发; 进程启动时仍处于 `sending` 的 `kind=send` 行同样置为 `unknown`
- 例外是 GitHub: 对 `unknown` 行, GitHub provider 按 7.2 的标记在目标线程最近 100 条评论中查找, 找到即回填 `platform_message_id` 并置为 `sent`, 确认找不到才按 7.4 的平台出站规则重发一次, 查找本身失败则保持 `unknown`
- QQ 的 `unknown` 行由调用方决定是否用新的 `idempotency_key` 再发, 路由层不替它决定
- 进程启动时仍处于 `sending` 的 `kind=webhook` 行回退为 `queued`, 因为接收方按 `X-HX-Router-Delivery` 去重, 重复投递是安全的
- 因此路由层唯一可能出现重复出站的情况是调用方主动换键重发, 这与 qq-napcat 与 github-app 两份文档的说法一致

### 7.4 重试矩阵

| 类别                        | 可重试的情形                                                           | 退避                                              | 次数与时长上限                                                                               | 用尽后                        |
| --------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------------- | ----------------------------- |
| 平台出站 `kind=send`        | 连接被拒绝, HTTP 502, 503, 504, 容器正在重启, GitHub 5xx               | 2 秒起步翻倍, 单次上限 60 秒, 叠加 20% 随机抖动   | 最多重试 3 次 (共 4 次尝试), 约 15 秒内结束                                                  | `failed`                      |
| 平台出站的限流等待          | 本地令牌桶不足, GitHub 返回 `Retry-After` 或 `X-RateLimit-Remaining=0` | 等到令牌或平台给出的时间点                        | 不计入重试次数, 单次等待上限 15 分钟, `give_up_at` 为创建后 24 小时                          | 超过 `give_up_at` 置 `failed` |
| webhook 投递 `kind=webhook` | 连接失败, 超时, 非 2xx                                                 | 10 秒起步翻倍, 单次上限 1 小时, 叠加 20% 随机抖动 | 不限次数, 以时长为界, `give_up_at` 为首次尝试后 24 小时                                      | `dead`                        |
| 入站事件补投                | QQ 上报丢失, GitHub 投递失败                                           | 不由路由层重试                                    | QQ 在实例回到 online 时按会话补拉最近 20 条, GitHub 只在用户手动触发时经 deliveries 接口补投 | 走同一套入站去重              |

- 401 (GitHub installation token 失效) 先强制刷新 token 再重试 1 次, 计入平台出站的重试次数
- 不可重试错误 (参数错误, 目标不存在, 权限不足, 风控类错误) 直接进入终态, 风控类错误另外触发第 9.3 节的熔断
- webhook 按 route 串行投递, 同一 route 的下一批要等上一批成功或 `dead`, 不同 route 之间互不阻塞
- webhook 时长核算: 10, 20, 40, ..., 2560 秒共 9 次退避约 1.4 小时, 之后每小时 1 次直到 24 小时, 因此接收端停机 1 小时后恢复, 最迟在下一次退避到点时 (不超过 1 小时) 收到补投, 停机超过 24 小时的批次进入 `dead`
- 一条 webhook route 进入 `dead` 的批次之后, route 继续从下一批投递, `dead` 批次可在前端手动重投

### 7.5 入站去重

- 入站唯一键为 `(instance_id, dedup_key)`, 唯一索引是永久的, 不表达时间窗口
- QQ 的 `dedup_key` 为 `qq:<message_id>:<time>`: NapCat 重投同一事件时两者都相同会被吸收; NapCat 的 `message_id` 是否在容器重启后复用需复核, 即使复用, 不同时间的新消息因 `time` 不同不会被误吸收, 这替代了 qq-napcat 早先提出的 10 分钟窗口
- GitHub 的 `dedup_key` 见第 3.4 节, edited 事件命中已有 `dedup_key` 时只覆盖 `text`, 不新增行
- GitHub 另有投递层去重: `router_ingress_deliveries` 以 `(instance_id, X-GitHub-Delivery)` 为主键, 命中直接返回 200 且不再处理
- 入库统一用 `INSERT ... ON CONFLICT DO NOTHING` (edited 用 `DO UPDATE SET text`), 命中时返回 `stored=false`
- 保留期清理 (第 10 节) 删除的旧行不再参与去重, 超过保留期的重投会被当作新消息, 这一窗口对 QQ 由 `time` 保证无害, 对 GitHub 由投递层去重表的 7 天保留覆盖手动重投的常见窗口

## 8. 配置, 密钥与 API Key

### 8.1 配置与密钥存储

所有平台密钥都进入 `messaging_instances.config_encrypted`, 整体 JSON 用 `security.encrypt_secret(settings, value)` 加密, 读取用 `security.decrypt_secret`

| 配置键                    | 平台   | 说明                                            | API 返回 |
| ------------------------- | ------ | ----------------------------------------------- | -------- |
| `event_token`             | QQ     | NapCat 上报时携带的鉴权 token, 沿用现有生成逻辑 | `***`    |
| `api_base_url`            | QQ     | 内置引擎容器的 OneBot HTTP 地址                 | 原值     |
| `rate_profile`            | QQ     | `conservative` 或 `default`, 决定令牌桶参数     | 原值     |
| `app_id`                  | GitHub | GitHub App ID                                   | 原值     |
| `client_id`               | GitHub | GitHub App Client ID                            | 原值     |
| `app_slug`                | GitHub | App slug, 决定 bot 登录名 `<app-slug>[bot]`     | 原值     |
| `private_key_pem`         | GitHub | App 私钥 PEM 全文                               | `***`    |
| `webhook_secret`          | GitHub | App webhook secret                              | `***`    |
| `webhook_secret_previous` | GitHub | 轮换期间的上一个 secret, 轮换完成后删除         | `***`    |

全局开关

- 设置项 `router_enabled`, 取值 `true` 或 `false`, 默认 `true`; 为 `false` 时不挂载 `/mcp` 与 `/api/v1/router`, 不启动 housekeeping, 用于 ADR 0005 的 A1 到 A3 对照测量
- 设置项 `router_message_retention_days`, 默认 90, 最小 7, 见第 10 节

其它

- route 的外部 webhook URL 与其 `webhook_secret` 加密存入 `router_routes.target_encrypted`
- GitHub installation token 只在内存缓存, 不落库, 进程重启后重新换取
- `.env` 与日志中不出现任何上述明文, 日志里的 session 地址保留, 消息 `text` 默认不写日志

### 8.2 路由 API Key

- 现有外部 API 的 Key 存在全局设置 `external_api_key` 与 `external_api_keys` 里且为明文比较, 不绑定用户, 不能复用为路由 API Key
- 路由 API Key 按用户签发, 明文格式为 `hxr_` 加 32 字节随机数的 base64url 编码, 只在 `POST /api/v1/router/api-keys` 的响应里返回一次
- 服务端只存 SHA-256 哈希 (`key_hash`) 与明文前 8 个字符 (`key_prefix`, 用于前端辨认), 校验时对传入值求哈希后按唯一索引查找
- 每个用户最多 20 把未吊销的 Key, 超出时创建返回 409
- 吊销即在 `revoked_at` 写入时间, 立即生效, 已建立的 SSE 连接与 MCP 会话在下一次请求或下一帧时断开; 吊销不可撤销, 吊销后的行保留用于审计
- 每次成功鉴权更新 `last_used_at`, 同一 Key 每分钟最多写一次, 避免把读请求变成写请求
- 删除用户时级联吊销其全部 Key

## 9. 速率整形, 熔断与错误码

### 9.1 QQ 限流

令牌桶按实例计算, REST, MCP, 前端发送与内部自动化共用同一个桶; 以下全部是本项目经验值, 腾讯不公开风控阈值, 这些数字不是平台限制; 上线后以测试小号 14 天运行记录为依据调整, 只允许往更保守的方向调, 放宽必须有记录支撑

| 维度                                | `default`                 | `conservative`               |
| ----------------------------------- | ------------------------- | ---------------------------- |
| 同一 session 最小间隔               | 3 秒                      | 6 秒                         |
| 同一 session 每分钟                 | 10 条                     | 5 条                         |
| 账号级突发                          | 3 条, 之后每秒补 1 个令牌 | 2 条, 之后每 3 秒补 1 个令牌 |
| 账号级每分钟                        | 20 条                     | 8 条                         |
| 账号级每小时                        | 300 条                    | 120 条                       |
| 账号级每天 (自然日按 Asia/Shanghai) | 1000 条                   | 300 条                       |
| 每次发送附加随机抖动                | 0.5 到 1.5 秒             | 1 到 3 秒                    |
| 单条长度                            | 1500 字符                 | 1500 字符                    |

- QQ 空间评论不进这张表, 走独立的 `qzone` 档 (docs/providers/qq-zone.md 4): 空间与聊天同号, 但各有一个桶, 空间的风控类失败同样计入 9.3 的熔断, 熔断会同时停掉聊天与空间的出站
- 单条 1500 字符是保守取值, QQ 客户端的实际单条上限需复核, 复核方法是用测试小号分别发送 1500, 3000, 4500 字符的纯文本并记录是否截断或失败
- 同一内容发往多个会话 (内容相同以去除空白后的 SHA-256 判定) 额外受限: 相邻两个会话间隔不少于 8 秒再加 0 到 4 秒抖动, 同一内容每天最多发往 20 个会话, 超出返回 `rate_limited`

### 9.2 GitHub 限流

- 账号级 (每个 installation) 每分钟 30 次写操作, 突发 5 次, 不设每日上限, 同一 installation 的写入串行执行
- 这是本项目经验值, 目的是给 GitHub 的二级速率限制留余量; GitHub 主速率与二级速率限制的当前数字需复核, 复核方法是查阅 docs.github.com 的 "Rate limits for the REST API" 页面并记录日期, 实现上以响应头 `Retry-After`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` 为准, 不硬编码平台数字
- 单条评论正文上限按 65536 字符处理, 需复核, 复核方法是用测试仓库提交超长评论观察 422 的边界; `max_text_length` 取 4000 (入参上限) 与该值的较小者

### 9.3 风控熔断

- provider 的 `SendResult.risk_signal=true` (OneBot 返回含风控, 频繁, 账号异常, 冻结等文案, 或收到下线, 冻结通知) 计为一次风控类失败
- 5 分钟内 3 次风控类失败, 或收到一次冻结与下线通知, 该实例出站置为 `held` 30 分钟; 当天第二次进入 `held` 时暂停 6 小时; 当天第三次直接置为 `manual_hold`
- `held` 到期自动恢复为 `open`; `manual_hold` 只能由用户调用 `POST /instances/{instance_id}/outbound/resume` 解除; 用户也可以随时调用 `hold` 接口进入 `manual_hold`
- 熔断期间接收照常, 只停发送; 期间新提交的 `kind=send` 行以 `held` 状态入队, 恢复后按原顺序继续, 仍受 7.4 的 `give_up_at` 约束
- 熔断与解除都写入实例事件, 并在 `sources_list` 中可见
- GitHub 实例同样适用 `manual_hold`, 自动熔断对 GitHub 只由 `abuse` 类 403 触发

### 9.4 错误码

| code                   | 含义                                                                 | retryable                      |
| ---------------------- | -------------------------------------------------------------------- | ------------------------------ |
| `session_not_found`    | 地址无效或不属于当前用户                                             | false                          |
| `session_not_sendable` | 仓库地址缺少 title, 或 QQ 目标不在好友与群列表中, 或向陌生号首发私聊 | false                          |
| `text_too_long`        | 超过该平台的 `max_text_length`                                       | false                          |
| `rate_limited`         | 本地整形拒绝且 `wait_seconds` 内无法投递, 消息已入队                 | false, 已排队无需重试          |
| `outbound_held`        | 账号处于 `held` 或 `manual_hold`, 消息已以 `held` 入队               | false, 恢复后自动继续          |
| `provider_offline`     | 账号实例离线                                                         | true                           |
| `provider_error`       | 平台返回错误                                                         | 由 `SendResult.retryable` 决定 |
| `delivery_unknown`     | 平台调用结果未知, 状态为 `unknown`, 见第 7.3 节                      | false                          |
| `cursor_invalid`       | cursor 无法解析或属于其它实例                                        | false                          |

### 9.5 provider 结果从哪来

- `MessagingProvider.send` 返回 `SendResult{status, platform_message_id, retryable, risk_signal, error_code, error_message, retry_after_seconds}`, 字段定义见 ADR 0005 第 4 节
- 现有 `MessagingAdapter.send_message(target, text) -> str` 不能提供这些字段: 它没有 `reply_to` 入参, `OneBotAdapter` 把全部网络异常与非零 retcode 都包成只带文案的 `MessagingError`, 超时与连接被拒绝无法区分, retcode 与 `wording` 也不再是结构化字段
- 因此 QQ provider 不包装 `send_message`, 而是调用 `OneBotAdapter` 新增的公开方法 `call_action(action, params)`, 它不抛业务异常, 返回 `{transport, http_status, retcode, wording, data}`, 其中 `transport` 取 `ok`, `timeout`, `connect_error`, `http_error`; QQ provider 按 qq-napcat 第 5.5 节把它映射成 `SendResult`
- 抽象基类 `MessagingAdapter` 的签名不改, 现有前端路径与其它适配器不受影响; 改动的是 `OneBotAdapter` 多出一个公开方法, 这需要在实现提交里带上对应 note
- GitHub provider 是新代码, 直接按 `SendResult` 返回, 不经过 `MessagingAdapter.send_message`

## 10. 保留期, 清理与 SQLite 写入

### 10.1 保留期

| 对象                            | 保留期                                                       | 依据                           |
| ------------------------------- | ------------------------------------------------------------ | ------------------------------ |
| `messaging_messages`            | `router_message_retention_days`, 默认 90 天, 按 `created_at` | 用户可调, 最小 7 天            |
| `router_outbox` 终态行          | 7 天, 按 `updated_at`                                        | 等于出站幂等窗口               |
| `router_outbox` 非终态行        | 不清理, 由 `give_up_at` 推进到终态后再计 7 天                | 防止删掉仍在投递的行           |
| `router_ingress_deliveries`     | 7 天, 按 `received_at`                                       | 覆盖 GitHub 手动重投的常见窗口 |
| `router_routes` 中 `expired` 行 | 过期后 7 天删除, 连同其 `kind=webhook` 的 outbox 行          | 便于用户查看最近过期的订阅     |
| `router_api_keys` 已吊销行      | 不删除                                                       | 审计                           |

### 10.2 清理方式

- 由 60 秒一次的 housekeeping 执行, 不新增定时器; 每次 tick 每张表最多删除 500 行, 一张表一个短事务, 删除量大时分多个 tick 完成, 避免长时间持有写锁
- 消息行按 `created_at` 索引删除, 删除前读出该批行的非空 `raw_ref`

### 10.3 raw 落盘文件的回收

- 落盘路径固定为数据目录下的 `router_raw/<yyyy>/<mm>/<dd>/<messaging_messages.id>.json`, 日期取落库日期 UTC
- 消息行删除事务提交之后再删除对应文件; 文件删除失败只记日志, 由下面的孤儿扫描兜底
- 孤儿扫描每天一次, 由 housekeeping 在 UTC 03:00 之后的第一个 tick 执行: 删除早于保留期的整个日期目录, 并删除日期目录内找不到对应消息行的文件
- 写入顺序是先写文件再提交消息行, 提交失败时立即删除刚写的文件

### 10.4 SQLite 写锁与 busy_timeout

- 现有 `database.connect` 以 `sqlite3.connect(..., timeout=30)` 打开连接并设置 `PRAGMA journal_mode=WAL`, 即每个连接的 busy timeout 为 30 秒, 路由层沿用同一个 `connect`, 不另开连接池
- WAL 下读不阻塞写, 但同一时刻只有一个写事务; 路由层所有写事务必须短: 不在事务内做网络调用, 不在事务内写 raw 文件
- 入站一条消息一个事务; outbox 领取到期行用 `BEGIN IMMEDIATE` 加 `UPDATE ... SET status='sending' WHERE id=? AND status IN ('queued','held')` 的比较并交换, 拿到行后提交, 平台调用完成后再开新事务写结果
- 等锁超过 30 秒抛出 `database is locked` 时: 入站返回 HTTP 503 让平台按自身行为重投 (QQ 的补拉与 GitHub 的手动重投都走入站去重), outbox 与 housekeeping 记日志后在下一个 tick 重试
- 路由层不调用 `VACUUM`; WAL checkpoint 沿用 SQLite 默认的自动 checkpoint

## 11. 分阶段落地

### 阶段 1: QQ 收发与 GitHub 事件监听

- 范围: `server/router/` 骨架, QQ provider, GitHub provider 的入站部分 (第 3.4 节全部事件), `messages_pull`, `message_send` (仅 QQ), `sources_list`, `sessions_list`, `session_select`, `delivery_status`, 新列与去重唯一索引, outbox 表, ingress 去重表, API Key 表与管理接口, 保留期清理
- 里程碑: 用 MCP Inspector 连接 `/mcp`, 选定一个 QQ 群, 调用 `message_send` 发出消息并在 QQ 客户端看到, 群里回复后用返回的 cursor 调 `messages_pull` 只读到这条回复, 对测试仓库评论后同样能 pull 到对应 envelope
- 验收: 同一 `idempotency_key` 调用两次只发出一条且第二次带 `deduplicated=true`, NapCat 重投同一事件只落库一行, 连发 5 条时相邻两条的发送间隔不小于 3 秒, 模拟平台超时后该行为 `unknown` 且不自动重发

### 阶段 2: 订阅与推送

- 范围: `hub.py`, `route_subscribe`, `route_unsubscribe`, `routes_list`, `events_wait`, `route_ack`, MCP resource 通知, SSE 流, REST 兼容面全部路由
- 落地情况 (2026-11-08): hub, 持久订阅, 长轮询与 SSE 改协程, 前端 "消息订阅" 页与接入示例已完成, 实际接口见 5.13; MCP resource 通知移到 MCP 补全阶段
- 里程碑: MCP 客户端订阅一个 QQ 群后, 群内新消息在 1 秒内触发 `notifications/resources/updated`, 断开重连后从 `ack_cursor` 续读无遗漏
- 验收: ADR 0005 的 A1, A2, A3, A6 全部通过

### 阶段 3: 出站 webhook 与 GitHub 发送

- 范围: webhook 类型 route 及其签名与退避, GitHub provider 的评论, 回复行内评论与建 issue, 结果未知时的标记查重, 风控熔断与 hold, resume 接口
- 落地情况 (2026-11-08): webhook 订阅的签名投递, 退避, dead 与重投, WebSocket 订阅流, 前端订阅页的 Webhook 与 WebSocket 已完成, 见 5.14; GitHub 评论, 行内回复与建 issue, 标记查重, 熔断与 resume 归入后续的 GitHub 补全阶段
- 里程碑: 一条 webhook route 把 QQ 群消息投递到外部接收端并通过签名校验; 接收端停机 1 小时后恢复, 积压消息在恢复后 1 小时内按序补投完成; 通过 MCP 对 issue 发评论并在 GitHub 上看到由 App 身份发出
- 验收: ADR 0005 的 A4, A5 通过; 模拟 5 分钟内 3 次 OneBot 风控类错误后该账号出站进入 `held` 并在 30 分钟后自动恢复; 模拟 GitHub 评论请求超时且评论实际已创建时, 该行经标记查重回填为 `sent` 且 GitHub 上只有一条评论

### 阶段 4: 前端切换与新平台

- 范围: 现有前端消息页改用 cursor 读取, `registry.py` 中 QQ 描述与 NapCat 实际路径对齐, 按需新增 Telegram 或企业微信 provider
- 里程碑: 新增一个 provider 的变更只涉及 `server/router/providers/` 与注册表一行, `server/router/` 其余文件零改动
- 验收: 新 provider 的 pull 与 send 通过阶段 1 的同一套用例

## 12. 测试清单

- `server/tests/test_router_cursor.py` 覆盖 cursor 编解码, 增量读, 越界与跨实例 cursor 拒绝, 清理后 cursor 的 `gap=true`
- `server/tests/test_router_outbox.py` 覆盖两类幂等键, 令牌桶间隔, 重试矩阵的次数与 `give_up_at`, 熔断与恢复, 重启时 send 行置 `unknown` 与 webhook 行回退 `queued`
- `server/tests/test_router_ingress.py` 覆盖 OneBot 事件去重, 同 `message_id` 不同 `time` 不被吸收, GitHub 签名校验失败返回 401, delivery 去重, edited 覆盖 text
- `server/tests/test_router_mcp.py` 用 MCP SDK 的内存传输调用全部 tool, 校验入参 schema 拒绝多余字段
- `server/tests/test_router_retention.py` 覆盖保留期删除分批, raw 文件随行删除与孤儿扫描, API Key 吊销后立即拒绝
- `server/tests/test_router_idle.py` 在 CI 中只校验 "无订阅时路由层除 housekeeping 外没有定时任务", 真实 CPU 与内存验收项 A1 到 A6 在部署机上手工执行并记录到实现 note
