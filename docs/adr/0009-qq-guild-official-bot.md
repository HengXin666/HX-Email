# 0009 QQ 频道走官方机器人 API, 作为独立平台接入

## Status

Accepted (2026-11-09). 取代 `docs/providers/qq-napcat.md` 第 0 节 "不使用任何 QQ 官方机器人渠道" 这一条约束; 该节其余约束 (不自研协议, 账号稳定性优先, 内存与 CPU 优先级) 不变, 并已在原处标注取代关系与本文链接.

## Context

需求要求覆盖 QQ 频道 (guild / 子频道). 原方案 (`docs/providers/qq-napcat.md` 第 0 节) 规定只用个人 QQ 号经 NapCat 收发, 不使用任何官方机器人渠道. 但 NapCat 不支持频道:

- NapCat issue #1828 (2026-05-10): `get_guild_list` 返回 `data: null`, `get_guild_channel_list`, `send_guild_channel_msg`, `get_guild_msg` 返回 "不支持的Api"; 维护者 2026-05-12 回复 "频道不支持哦" 并关闭.
- NapCat issue #15 (2024-05): 维护者表示不会加频道接口.

剩下的路只有两条:

- A. QQ 开放平台官方机器人 API: 机器人身份 (AppID + AppSecret), webhook 回调 (Ed25519 签名), OpenAPI 发消息. 不碰个人号.
- B. 按 go-cqhttp 的频道接口实现, 只能由 icqq 一类协议端提供, 这类协议端需要用个人号走旧协议登录, 冻结风险高, 正与原方案 "账号稳定性第一" 冲突.

## Decision

- 采用 A. QQ 频道是一个独立平台 `qqbot`, 独立的实例类型, 独立的能力声明 (`risk_level=official`, `rate_profile=qqbot`), 独立的 provider 与回调端点 `/api/v1/router/ingress/qqbot/{instance_id}`.
- 不动 NapCat 那条线: `qq` 平台 (私聊, 群, 临时会话, QQ 空间) 仍只用个人号, 不接任何官方机器人能力; 两个平台不共享实例, 整形桶与熔断.
- 地址: `qqbot:<iid>/guild/<guild_id>/channel/<channel_id>`, 存储键 `qqbot:<iid>:channel:<guild_id>/<channel_id>`.
- 本阶段只接文字子频道消息 (`AT_MESSAGE_CREATE`, `MESSAGE_CREATE`) 与往子频道发文本; 频道私信, 论坛帖子, 表情表态, 群聊与单聊机器人消息不在本次范围.

## Consequences

- 机器人与个人号是两个身份: 用户在频道里看到的是机器人, 不是自己的 QQ 号; 公域机器人只能收到 @ 它或回复它的消息, 收全部消息需要申请私域.
- 主动消息受平台限量 (默认每个子频道每天 20 条, 每个频道每天 2 个子频道), 被动回复只在原消息 5 分钟内有效; 路由层把限量错误当作限频重试, 把过期当作终态失败.
- 开放平台要求 HTTPS 回调地址, 端口只能是 80, 443, 8080, 8443; 部署需要公网可达的 HTTPS 入口.
- 官方文档写明发消息接口要求机器人 "连接到 websocket 上保持在线状态", 而 webhook 与 websocket 二选一; webhook 模式下发消息是否受此限制需复核 (docs/providers/qq-bot.md 8).
- 原 "不使用任何 QQ 官方机器人渠道" 的约束不再是全局规则, 只约束 `qq` 平台本身.

## Links

- 被取代的约束: [`docs/providers/qq-napcat.md` 第 0 节](../providers/qq-napcat.md#0-需求边界)
- provider 规格: [`docs/providers/qq-bot.md`](../providers/qq-bot.md)
- 决策记录: `.agents/notes/implemented/feature/2026-11-09-qqbot-guild.md`
