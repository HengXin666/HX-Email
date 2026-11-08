# Agent Note: GitHub 事件补全, 触发信号由 provider 计算并随行落库

Status: implemented

Decision-ID: github-events-triggers

## Code

- `server/src/hx_email/server/router/providers/impl/github/github_events.py`
- `server/src/hx_email/server/router/impl/store.py`
- `server/src/hx_email/server/contract/event.py`

## Problem

GitHub provider 只把 4 类事件里 action 为 created 或 opened 的映射成消息, 与 docs/providers/github-app.md 3.1 的清单差得多, 也撑不起 Agent harness 需要的触发方式:

1. 事件类型缺口: `pull_request_review` 被丢弃; issue 与 PR 的 closed, reopened, ready_for_review 只改会话元数据; 评论 edited 不改正文; discussion, discussion_comment, commit_comment, push 完全没有. manifest 甚至没订阅 `pull_request`, 新开 PR 根本不会投递.
2. 触发判定缺口: `flags.mention_self` 与 `reply_to_self` 对 GitHub 恒为 `null`, `mentions` 恒为空; 订阅 filter 的 `mention_self` 因此永远匹配不到 GitHub 消息. `kind` 只能按 `platform_message_id` 前缀猜, 状态消息与它所在线程同前缀, 猜不出来.
3. 存储里没有这些信号, 读取时也无从推导: `@` 是否提及本 App 需要 App slug, 是否回复本 App 需要上一条消息的发送者.

## Decision

- 拆出 `github_mapping.py`: 签名, 线程 (`Thread`) 与草稿 (`Draft`) 结构, `@` 提及解析, 时间换算, 以及把草稿连同触发字段一起变成 envelope 的 `to_envelope`. `github_events.py` 只保留每类事件的取值与分发表 `MAPPERS`, 并重新导出旧名字.
- 事件补全: issue_comment, pull_request_review_comment, discussion_comment 的 created 与 edited (edited 置 `edit` 覆盖正文); commit_comment created; pull_request_review submitted (正文为空的 commented review 跳过); issues, pull_request 的 opened 为 `thread_opened`, closed, reopened, ready_for_review 为 `thread_state` (固定模板, `dedup_key` 加 action 与投递 id); discussion created; push 每个 distinct 提交一条 `commit`. 非新建 action 照旧产出会话元数据更新.
- 地址: 能力声明增加 `discussion` (`{repo}#{n}`) 与 `commit` (`{repo}@{sha}`) 两个只收不发的 kind; 仓库选择器自动覆盖这两类会话. event_kinds 增加 `thread_state`, `review`, `commit`, signals 声明全部三个.
- 触发信号由 provider 计算: `mentions` 在去掉标记的正文里找 `@login`, 跳过代码与邮箱; 提及本 App (`slug` 或 `slug[bot]`) 即 `mention_self`; 线程由本 App 开出时线程内他人消息即 `reply_to_self`; 本 App 自己的消息两者恒为 false.
- 落库: `messaging_messages` 新增 `trigger_json` 列存 `{kind, mentions, flags}`; `validate_inbound` 校验这三个可选字段; `store_inbound` 对带 `reply_to` 的消息查同实例上一条, 它是本账号发出的就补 `reply_to_self`, 编辑时一并改写触发字段. 读出时 Envelope 带回这些字段, `event_view` 优先使用, 旧行仍按前缀推导, 推导不出的信号给 `null` 而不是 false.
- manifest 默认事件补 `pull_request`, discussion 两类, `commit_comment`, `push`; 权限增加 Contents 与 Discussions 只读.

## Alternatives considered

- 什么都不做, 继续只映射 created 与 opened: 最强理由是 App 权限最小, 改动为零. 否决: PR 新开都收不到, `mention_self` 对 GitHub 永远是 null, "被 @ 触发" 与 "被回复触发" 两条核心路径不可用.
- 复用现有读取时推导, 在 `event_view` 里算 mention 与 reply: 最强理由是不加列不迁移. 否决: 读取侧没有 App slug, 也不该为每条消息再查一次父消息; 而且编辑后的信号需要和正文一起改写, 只能在写入时做.
- 把 mention 与 reply 的判定放进路由层做成平台无关规则: 最强理由是 QQ 频道等以后可复用. 部分采纳: 按 `reply_to` 查父消息是平台无关的, 放在 store; `@login` 的语法与 "谁是本 App" 是 GitHub 专有的, 留在 provider. 只有上报了触发字段的 provider 才做父消息查询, QQ 的 `reply_to_self` 仍是 null.
- 不订阅 push, 只收 commit_comment: 最强理由是可以只申请更少的事件. 否决: 两者都需要 Contents 只读, 权限面相同; 提交说明里的 `@` 与 "有新提交" 都是常见触发.
- 为每类线程状态单独起消息 id 前缀: 最强理由是 kind 能继续靠前缀推导. 否决: 文档 3.3 规定状态消息沿用线程对象的 id 前缀并在 dedup_key 上区分; 既然 kind 已随行存储, 不必再发明前缀.

## Consequences

- 已安装的 App 需要仓库所有者在 GitHub 上确认新增的 Contents 与 Discussions 只读权限, 并勾选新事件; 新建的 App 默认就有.
- discussion 与 commit 会话目前只收不发; 在 discussion 下回复与提交评论的发送属于后续阶段.
- 本次之前入库的 GitHub 行没有 `trigger_json`, 它们的 `mention_self` 与 `reply_to_self` 为 null, 订阅的 `mention_self` 过滤不会命中旧行.
- 父消息查询只在本实例内按 `message_id` 匹配, 父消息不在库里 (例如 App 安装前的评论) 时 `reply_to_self` 保持 provider 给出的值.
- 没有用真实 GitHub App 联调, 事件载荷取自 GitHub 文档字段, 需复核 discussion 与 commit_comment 的实际投递.
