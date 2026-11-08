# Agent Note: QQ 频道作为独立的官方机器人平台 qqbot 接入

Status: implemented

Decision-ID: qqbot-guild

## Code

- `server/src/hx_email/server/router/providers/qqbot.py`
- `server/src/hx_email/server/router/providers/impl/qqbot/qqbot_events.py`
- `server/src/hx_email/api/impl/router/ingress/ingress_qqbot.py`

## Problem

需求要求覆盖 QQ 频道. NapCat 不支持频道接口 (issue #1828, 2026-05-12 关闭), 而 `docs/providers/qq-napcat.md` 第 0 节规定不使用任何官方机器人渠道. 不改这条约束就无法接入频道.

## Decision

- 用户选定方案 A (2026-11-08): 走 QQ 开放平台官方机器人 API, 作为独立平台 `qqbot`, 不动 NapCat 那条线; 新增 ADR 0009 取代旧约束, 两边互链.
- 地址 `qqbot:<iid>/guild/<g>/channel/<c>`, 存储键 `qqbot:<iid>:channel:<g>/<c>`; 能力声明 `risk_level=official`, `rate_profile=qqbot`.
- 入站: webhook 回调, Ed25519 验签, op 13 自动回签; 子频道消息同步入库 (放到线程里) 并唤醒订阅.
- 出站: access_token 缓存与刷新, `POST /channels/{id}/messages`; `reply_to` 有值即被动回复; 错误码按限频, 风控, 鉴权, 过期, 审核分类.
- 实例: `PluginKind` 加 `router_only`, 允许通用接口建实例 (必须带 app_id 与 app_secret), `app_secret` 只写不读.

## Alternatives considered

- 什么都不做, 声明频道不支持: 最强理由是保持原约束与单一身份. 否决: 需求明确要频道, 而 NapCat 侧没有任何实现路径.
- 方案 B, 按 go-cqhttp 频道接口对接 icqq 一类协议端: 最强理由是仍用个人号, 用户在频道里以自己身份出现. 否决: 需要换用旧协议登录个人号, 冻结风险正与 "账号稳定性第一" 冲突.
- 把官方机器人做成 `qq` 平台下的一个 kind: 最强理由是地址都以 `qq:` 开头, 消费者少认一个平台. 否决: 实例类型必须与地址平台一致, 而机器人与个人号是两个身份, 两套鉴权, 两种风控等级; 混在一个平台会让整形与熔断互相牵连.
- 用 websocket 网关而不是 webhook 接收: 最强理由是官方文档说发消息要求机器人连在网关上. 暂不采纳: 网关需要常驻连接, 心跳与断线重连, 与本项目 "空闲零 CPU" 的取向不符; webhook 与现有 GitHub 入站同构. 是否必须连网关列入需复核.

## Consequences

- 部署需要公网 HTTPS 回调地址 (端口 80, 443, 8080, 8443).
- 公域机器人只收得到 @ 它或回复它的消息; 主动消息按子频道每天限量.
- 机器人收不到自己发的消息, `from_self` 只出现在出站记录上.
- 前端实例页没有专门的机器人配置表单, 目前通过 API 建实例与改配置.
- 没有用真实机器人联调, 复核项见 docs/providers/qq-bot.md 8.
