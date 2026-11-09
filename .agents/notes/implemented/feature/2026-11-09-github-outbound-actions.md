# Agent Note: GitHub 出站动作经 action_invoke 走同一条 outbox

Status: implemented

Decision-ID: github-outbound-actions

## Code

- `server/src/hx_email/server/contract/github_actions.py`
- `server/src/hx_email/server/gateway/sending.py`
- `server/src/hx_email/server/gateway/impl/dispatch.py`
- `server/src/hx_email/server/router/provider.py`
- `server/src/hx_email/server/router/providers/github.py`
- `server/src/hx_email/server/router/providers/impl/github_reactions.py`
- `server/src/hx_email/server/router/providers/impl/github_write/actions.py`
- `web/src/api/endpoints/router_github.ts`
- `web/src/pages/impl/GithubOutboundSettings.tsx`

## Problem

阶段 4b 要让 GitHub 的出站动作 (评论, 表情, 提交 review, 建 discussion, discussion 评论) 可以被调用, 并能按实例关掉其中一些. 此前出站只有 `message_send` 一条路, 能力声明里的 `actions` 只是展示用的数据, 没有通用入口去执行它们. discussion 没有 REST 写接口, 只能走 GraphQL, 且要先拿到仓库, 分类, discussion 的 node id.

## Decision

- 能力声明即契约: `ActionSpec` 带 `params` (`ParamSpec`: 必填, `choices`, `pattern`, `max_length`, 条件必填 `required_if_param` 与 `required_if_values`), `capabilities_list` 原样输出. GitHub 的动作声明单独放在 `contract/github_actions.py`. 网关 `invoke_action` 只按声明校验动作名, 目标地址种类与参数, 不认识的键直接拒绝. 错误码 `action_not_supported`, `invalid_payload`, 都映射为 422, 不入队.
- 动作与 `message_send` 共用 `router_outbox` 的 `kind=send` 行, payload 多带 `action` 与 `params`. 于是幂等键, 整形, 熔断, 重试, `delivery_status` 只有一份, 不新增表或线程. 有正文的动作 (`text` 或 `body`) 成功后写入消息流, 表情不写.
- provider 侧可选协议 `ActionProvider.invoke(session, ActionCall)`; dispatcher (`invoke_on`) 见到 payload 带 `action` 就调它, 不实现该协议的 provider 得到 `action_not_supported` 终态. GitHub 的分发表在 `impl/github_write/actions.py`, 让 `github.py` 保持在 300 行以内.
- GitHub 各动作:
  - `comment_create` 复用 `send` 的评论路径与隐藏标记.
  - `reaction_add` 调 REST reactions 接口, 平台对同一身份同一表情返回已有那条, 天然幂等, 超时按可重试处理.
  - `review_submit` 目标用 `issue` 地址 (PR 与 issue 共用编号, 地址模型没有单独的 PR 种类), 先用 GraphQL 只查 `__typename` 确认是 PR, 普通 issue 直接 `failed` (`invalid_payload`), 再 `POST /pulls/{n}/reviews`. 不可幂等, 写请求超时进 `unknown`.
  - `discussion_create` 与 `discussion_comment_create` 走 GraphQL. repositoryId, categoryId, discussion id 每次调用现查, 不缓存; 分类与评论列表按小页分页, 找到即停, 最多 20 页. 查询不写入, 超时可重试; mutation 超时进 `unknown`. `reply_to` 可以是 node id, 也可以是入站消息里看到的 `dc:<databaseId>` (分页查顶层评论换成 node id).
  - review 与 discussion 正文同样带隐藏投递标记, 留给以后的对账.
- 按实例开关: 实例配置键 `disabled_actions` (逗号分隔, 默认空即全部开启, 以后新增的动作也默认开启), 经已有的 `PUT /messaging/instances/{id}/config` 合并写入, App 凭据字段不变. `invoke_action` 在校验目标前检查, 被关掉返回 `action_not_supported`. 前端 `GithubOutboundSettings` 从能力声明读动作列表 (按 `platform` 取, 默认 `github`; GitHub 用户账号卡片传 `github_user` 复用同一组件), 每个动作一个开关; `message_send` 不在开关里.
- 入口: MCP 工具 `action_invoke`, REST `POST /api/v1/router/actions`; 动作枚举来自 REGISTRY; `action=message_send` 转给原有 `send_message`.
- 权限: manifest 的 Discussions 从只读改为读写. 已安装的 App 要所有者在 GitHub 上接受新权限后 discussion 动作才可用.
- 内存: 不加任何缓存; `params` 最多 8 个键, 每个值有长度上限; GraphQL 只取需要的 id 字段.

## Alternatives considered

- 什么都不做 / 复用现有 `message_send`, 用 `reply_to` 或特殊前缀编码表情, review 与 discussion: 最强理由是零新接口, 消费者少学一个工具. 否决: 表情和 review 结论不是消息, 塞进 `text` 会让整形, 记录出站消息, 对账全部出错, 也无法在能力声明里说清参数.
- 每个动作一个专用 MCP 工具和 REST 路由: 最强理由是每个工具的 JSON Schema 可以写得很精确. 否决: 每加一个平台动作都要改 MCP 目录, REST 路由和前端, 违背 "新平台只是一份声明加一个 provider" 的契约 v2 原则; 通用入口加声明里的 `params` 同样能让调用方拿到精确约束.
- 动作单独建一张 outbox 表或单独的分发线程: 最强理由是动作和消息的状态机可以各自演进. 否决: 幂等, 整形, 熔断都要再实现一遍, 还多一个常驻线程, 与小内存, 空闲零 CPU 的要求冲突.
- 缓存 repositoryId 与分类 id: 最强理由是每次建 discussion 省一到两次查询. 否决: 用户要求小内存, 不加缓存; 分类在 GitHub 上改名或删除后缓存会给出错的 id, 而建 discussion 是低频操作.
- review 不做 PR 预检, 直接 POST 让 GitHub 返回 404: 最强理由是少一次调用. 否决: 404 也可能是仓库不在安装范围, 调用方分不清 "不是 PR" 和 "没权限"; 预检只取一个字段, 代价很小.
- 动作开关用 `enabled_actions` 白名单: 最强理由是默认拒绝更保守. 否决: 存量实例没有该键时全部动作会突然失效, 新增动作也要每个实例手动打开; 黑名单默认空即全开, 与升级前行为一致.
- 表情也加隐藏标记做对账: 最强理由是与评论的结果未知处理一致. 否决: 表情没有正文放标记, 而平台本身对重复表情幂等, 重试就是最便宜的对账.

## Consequences

- 出站 `unknown` 行仍没有调用方去跑 `reconcile_unknown`; 它也只按标记查评论, 不查 review 与 discussion.
- 已安装的 App 在所有者接受 Discussions 读写前, discussion 动作返回 `permission_denied`.
- 关掉动作只拦新调用, 已入队的行照常投递. 重新走 manifest 创建 App 会重写配置, `disabled_actions` 被清空.
- GitHub App 提交的 APPROVE 是否计入分支保护的必需审批由仓库规则决定, 未核实.
- 没有用真实 GitHub App 联调, GraphQL 查询与错误类型按文档编写.
