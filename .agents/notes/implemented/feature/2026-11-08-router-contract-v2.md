# Agent Note: 路由契约 v2, 层级地址由平台声明, 存储仍用 v1, 读结果附加 Event v2 视图

Status: implemented

Decision-ID: router-contract-v2

## Code

- `server/src/hx_email/server/contract/address.py`
- `server/src/hx_email/server/router/envelope/session.py`
- `server/src/hx_email/server/router/impl/reader/source.py`

## Problem

网关要作为其它服务 (Agent harness 的 trigger 与 thread 订阅) 的统一消息基建, 下一批要接 QQ 频道, QQ 空间 (说说与评论), GitHub discussion 与 commit. v1 地址 `<platform>:<iid>:<type>:<peer>` 把类型放在 peer 前面:

1. "某仓库下全部 issue, PR, discussion, commit" 不是一个前缀, 订阅只能按类型拆成多条.
2. 频道 (guild/channel) 与空间 (主人/说说/评论) 是多层对象, 只能在 peer 里各自发明子语法, 这正是 ADR 0005 否决过的做法.
3. `envelope.PLATFORMS`, `SESSION_TYPES`, `reader.PLATFORMS` 与 MCP schema 的 enum 都写死 qq 与 github, 加平台要改核心.
4. envelope 没有事件种类, 线程, mention 与 reply 信号, "被 @ 触发 / 被回复触发" 无从表达.

## Decision

- 新目录 `server/contract/` (纯数据与纯函数, 不 import router 或 gateway): `capabilities.py` 定义平台声明 (地址 kind 树, id 段数与正则, v1 映射模板, 事件种类, 信号, 动作) 与注册表; `builtin.py` 声明 QQ 与 GitHub 已实现的能力并持有进程级 `REGISTRY`; `address.py` 解析 v2, 与 v1 双向转换, 把选择器翻译成 v1 的精确值加 LIKE 模式; `event.py` 在 v1 envelope dict 上附加 v2 字段.
- 存储键不变, 仍是 v1 `chat_id`. `envelope.parse_session` 与 `reader.parse_source` 遇到 v2 先转成 v1, 因此发送, 幂等, 出站队列, 去重全部沿用现有路径, 两种写法发往同一会话共享幂等键.
- 仓库级选择器 (`github:7/repo/o/r`) 需要 "仓库本身 OR 其下线程" 两种 chat_id, `Source` 增加 `patterns`, `build_query` 生成 `chat_id = ? OR chat_id LIKE ? ESCAPE '\'`; id 中的 `%` `_` `\` 全部转义 (仓库名常含 `_`).
- 核心的平台与类型集合改为读注册表; MCP 新增 `capabilities_list`, REST 新增 `GET /router/capabilities`, platform enum 由注册表生成.
- 读结果附加 `contract, address, thread, parent, kind, mentions, flags, segments`; 平台未上报的信号为 `null`, 与 `false` 区分, 让消费者知道 "没被 @" 和 "不知道有没有被 @" 不是一回事.
- 只声明已实现的能力; QQ 频道, QQ 空间, GitHub discussion 与 commit 在实现它们的阶段加入声明.
- 平台名可含下划线 (`github_user`): v1 地址的平台段按 `[a-z0-9_]+` 校验, 与能力声明的平台名规则一致.

## Alternatives considered

- 什么都不做, 继续用 v1 并在 peer 里扩展子语法 (如 `qq:3:channel:<guild>/<channel>`): 最强理由是零改动, 现有调用方与数据不受影响. 否决: 每种多层对象各自发明 peer 子语法, 前缀订阅仍然无法跨类型, 平台枚举仍写死, 新平台必须改核心.
- 直接把存储迁移到 v2 (改写 `messaging_messages.chat_id` 与 outbox 的 session): 最强理由是只有一种地址, 没有双向转换. 否决: 需要一次性数据迁移并改动去重与幂等的唯一键, 风险集中在已上线的收发路径上; 而转换是纯函数, 在入口处做一次即可, 以后要迁移时转换函数就是迁移脚本.
- v2 用百分号编码 id 中的 `/` (`repo/hx%2FHX-Email`) 代替按 kind 声明段数: 最强理由是解析器不依赖注册表. 否决: 地址主要给 LLM 与人读写, 编码后容易写错; 段数本来就是平台知识, 放在声明里正好.
- 在 `server/router/` 内加文件: 最强理由是离使用方近. 否决: 该目录已有 5 个 py 文件, 且契约应当不依赖 router, 才能被将来的 hub 与新 provider 共同引用而不产生循环导入.

## Consequences

- 加平台或加层级 = 在注册表里加一份 `PlatformCapabilities` 加一个 provider, 地址解析, 选择器, MCP enum, capabilities 输出自动跟上.
- `legacy_peer` 模板必须恰好引用该 kind 的整条祖先链, 声明时校验; 反向解析用非贪婪分组, 所以模板里相邻两个 id 之间必须有分隔字面量.
- mentions 与 flags 目前只在读出时派生, 不落库, 也不能用于过滤; 下一阶段 (hub 与持久订阅) 落库并接入订阅过滤.
- 两种地址并存期间, 返回值同时带 `session` (v1) 与 `address` (v2); 前端与调用方迁移完成后再考虑收掉 v1 入参.
