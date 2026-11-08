# Agent Note: GitHub 出站动作经 action_invoke 走同一条 outbox

Status: implemented

Decision-ID: github-outbound-actions

## Code

- `server/src/hx_email/server/gateway/sending.py`
- `server/src/hx_email/server/router/provider.py`
- `server/src/hx_email/server/router/providers/github.py`
- `server/src/hx_email/server/router/providers/impl/github_reactions.py`

## Problem

阶段 4b 要让 GitHub 的出站动作 (评论, 表情, 之后还有提交 review, 建 discussion) 可以被调用. 此前出站只有 `message_send` 一条路, 能力声明里的 `actions` 只是展示用的数据, 没有通用入口去执行它们. 本轮按用户缩小后的范围只做评论 (`comment_create`) 与表情 (`reaction_add`) 两类.

## Decision

- 能力声明即契约: `ActionSpec` 新增 `params` (`ParamSpec`: 必填, `choices`, `pattern`, `max_length`), `capabilities_list` 原样输出. 网关 `invoke_action` 只按声明校验动作名, 目标地址种类与参数, 不认识的键直接拒绝. 新错误码 `action_not_supported`, `invalid_payload`, 都映射为 422, 不入队.
- 动作与 `message_send` 共用 `router_outbox` 的 `kind=send` 行, payload 多带 `action` 与 `params`. 于是幂等键, 整形, 熔断, 重试, `delivery_status` 只有一份, 不新增表或线程.
- provider 侧新增可选协议 `ActionProvider.invoke(session, ActionCall)`; dispatcher 见到 payload 带 `action` 就调它, 不实现该协议的 provider 得到 `action_not_supported` 终态.
- GitHub: `comment_create` 复用 `send` 的评论路径与隐藏标记 (结果未知时可按标记对账); `reaction_add` 调 REST reactions 接口, 平台对同一身份同一表情返回已有那条, 天然幂等, 所以超时按可重试处理而不是 `unknown`. 表情没有正文, 不写入消息流.
- 入口: MCP 工具 `action_invoke`, REST `POST /api/v1/router/actions`; `action=message_send` 转给原有 `send_message`.
- 内存: 不加任何缓存; `params` 最多 8 个键, 每个值有长度上限, 入队前就截断在校验里.

## Alternatives considered

- 什么都不做 / 复用现有 `message_send`, 用 `reply_to` 或特殊前缀编码表情: 最强理由是零新接口, 消费者少学一个工具. 否决: 表情不是消息, 没有正文与长度语义, 塞进 `text` 会让整形, 记录出站消息, 对账全部出错, 也无法在能力声明里说清参数.
- 每个动作一个专用 MCP 工具和 REST 路由 (`reaction_add`, `review_submit` ...): 最强理由是每个工具的 JSON Schema 可以写得很精确. 否决: 每加一个平台动作都要改 MCP 目录, REST 路由和前端, 违背 "新平台只是一份声明加一个 provider" 的契约 v2 原则; 通用入口加声明里的 `params` 同样能让调用方拿到精确约束.
- 动作单独建一张 outbox 表或单独的分发线程: 最强理由是动作和消息的状态机可以各自演进. 否决: 幂等, 整形, 熔断都要再实现一遍, 还多一个常驻线程, 与小内存, 空闲零 CPU 的要求冲突.
- 表情也加隐藏标记做对账: 最强理由是与评论的结果未知处理一致. 否决: 表情没有正文放标记, 而平台本身对重复表情幂等, 重试就是最便宜的对账.

## Consequences

- 提交 review, 建 discussion, discussion 评论尚未声明, 调用会得到 `action_not_supported`; 下一轮按同样方式加 `ActionSpec` 与 `invoke` 分支即可. discussion 写权限 (`github_manifest.py` 仍是 read) 也留到那时.
- 前端还没有按实例开关动作的配置页, 本轮不做.
- 出站 `unknown` 行仍没有调用方去跑 `reconcile_unknown`, 与本轮之前相同.
- 没有用真实 GitHub App 联调.
