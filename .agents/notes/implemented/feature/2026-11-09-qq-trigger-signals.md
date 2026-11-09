# Agent Note: QQ (NapCat) 消息由 provider 上报触发信号

Status: implemented

Decision-ID: qq-trigger-signals

## Code

- `server/src/hx_email/server/router/providers/impl/qq_events.py`

## Problem

QQ 平台在能力声明里声明了 `from_self`, `mention_self`, `reply_to_self` 三个信号, 但 `to_envelope` 只产出 3.1 字段, 不带 `kind`, `mentions`, `flags`. 于是 `trigger_json` 为空, 视图里 QQ 消息的 `mention_self` 与 `reply_to_self` 恒为 `null`, `mentions` 恒为空, 订阅 filter 的 `mention_self` 对 QQ 永远匹配不到. 下游消费者 (dsh-superagent 的 hxrouter Source) 只能自己从正文的 `@<QQ 号>` 和会话历史里猜, 还得额外配置机器人 QQ 号, 因为 `/sources` 的 `account_id` 在实例刚建好时为空.

## Decision

- `to_envelope` 用 OneBot 事件自带的 `self_id` 计算触发字段: `kind` 固定 `message`; `mentions` 来自 `at` 段, 每个数字 QQ 号一项, `@all` 不算提及任何人, 上限 50 项; `mention_self` 为 `at` 段里出现 `self_id` 且不是本号自己发的; `from_self` 与 `sender.is_self` 同一判定.
- `reply_to_self` 由 provider 置 false, 交给 `store_inbound` 已有的按 `reply_to` 查上一条的逻辑补成 true, 与 GitHub, QQ 空间同一条路径, 不在 provider 里查库.
- 事件缺 `self_id` 时只给 `kind` 与 `mentions`, `flags` 留空, 视图仍报 `null`, 不把未知当成 false.

## Alternatives considered

- 什么都不做, 由消费者从正文推断: 最强理由是网关不动, 消费者已经实现了推断. 否决: 每个消费者都要重写同一套推断, 还都要配置机器人账号; 网关手里有 `self_id` 和 `at` 段这两个确定的事实, 推断只会更差.
- 在视图层按 `raw.self_id` 和 `raw.message` 现算: 最强理由是旧行也能补上信号. 否决: 视图层已约定优先用入库时存下的 `trigger_json`, 现算会让 QQ 成为唯一一个读时解析 raw 的平台; 旧行保持 `null` 与其它平台一致.
- 在 provider 里直接查上一条判断 `reply_to_self`: 最强理由是信号一次算全. 否决: 存储层已经统一做这件事, provider 不持有数据库连接.

## Consequences

- 用例在 `server/tests/test_router_qq.py`: 映射层四条 (`test_at_self_sets_mention_flags` 覆盖 @self 与 @all, `test_at_other_is_not_mention_self`, `test_own_message_never_mentions_self` 覆盖 from_self, `test_missing_self_id_leaves_flags_unknown` 覆盖缺 self_id), 外加 2026-11-10 补的一条入库链路 `test_stored_reply_and_mention_reach_view_and_filter`: 本号消息入库后, 回复它并 @self 的消息经 `store_inbound` 把 `reply_to_self` 从 false 补成 true, 视图 flags 与订阅 filter `mention_self` 都读得到, 且与 QQ 能力声明的三个信号一致.

- 新入库的 QQ 消息带 `trigger_json`, 订阅 filter 的 `mention_self` 对 QQ 生效; 本改动之前入库的 QQ 行仍是 `null`.
- 2026-11-09 用假 NapCat 对本机 dev 后端联调: 群里 `@<self_id>` 得到 `mention_self=true`, 回复本号出站消息得到 `reply_to_self=true`.
- 真实 NapCat 的 `at` 段字段 (`qq`, 可选 `name`) 以 OneBot 11 为准, 未用真号复核.
