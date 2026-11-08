# QQ 频道接入: 官方机器人 API (平台 `qqbot`)

QQ 频道不由 NapCat 接入 (NapCat 不支持频道), 改用 QQ 开放平台的官方机器人, 作为与 `qq` 平台并列的独立平台. 决策见 [ADR 0009](../adr/0009-qq-guild-official-bot.md), 被取代的旧约束见 `docs/providers/qq-napcat.md` 第 0 节

决策记录: `.agents/notes/implemented/feature/2026-11-09-qqbot-guild.md`

## 1. 范围

- 收: 文字子频道消息, `AT_MESSAGE_CREATE` (公域, @ 机器人或回复机器人) 与 `MESSAGE_CREATE` (私域, 全部消息)
- 发: 往子频道发文本; 带 `reply_to` 为被动回复, 不带为主动消息
- 不做: 频道私信, 论坛, 表情表态, 图片与 ark/markdown 消息, 群聊与单聊机器人

## 2. 接入步骤

1. 在 QQ 开放平台 (q.qq.com) 创建机器人, 记下 AppID 与 AppSecret
2. 建实例: `POST /api/v1/messaging/instances`, `{"kind": "qqbot", "name": "...", "config": {"app_id": "...", "app_secret": "..."}}`; `app_secret` 只写不读, 返回时打码; 沙箱环境可另填 `api_base`
3. 在开放平台的回调配置里填 `https://<公网域名>/api/v1/router/ingress/qqbot/<实例 id>`, 勾选 `PUBLIC_GUILD_MESSAGES` (私域机器人另勾 `GUILD_MESSAGES`); 平台会先发 op 13 验证, 本端自动回签
4. 回调地址只能是 HTTPS, 端口 80, 443, 8080, 8443

## 3. 地址与 envelope

| v2 地址                                             | v1 存储键                                     | 说明                       |
| --------------------------------------------------- | --------------------------------------------- | -------------------------- |
| `qqbot:<iid>/guild/<guild_id>`                      | 无 (只作分组)                                 | 选择器: 该频道下全部子频道 |
| `qqbot:<iid>/guild/<guild_id>/channel/<channel_id>` | `qqbot:<iid>:channel:<guild_id>/<channel_id>` | 文字子频道                 |

- `platform_message_id` 为平台消息 id, `dedup_key` 为 `qqbot:<消息 id>`; 公域与私域事件同时推送同一条消息时由去重键吸收
- `<@!id>` 换成 `@昵称` 并记进 `mentions`; mentions 里 `bot` 为 true 的视为提到本账号 (`mention_self`)
- `AT_MESSAGE_CREATE` 只在 @ 机器人或回复机器人时推送, 所以其中没 @ 到机器人的消息记为 `reply_to_self`; 带 `message_reference` 的消息另由入库时按 `reply_to` 查本账号消息补判
- 机器人收不到自己发的消息, 入站 `from_self` 恒为 false; 出站由分发器另记一行
- 时间取 `timestamp` (RFC 3339, +08:00) 换成 UTC `Z`; 附件只记引用, 不下载

## 4. 风控档位与限流

能力声明 `risk_level=official`, `rate_profile=qqbot`. 官方身份没有封号风险, 档位只为不撞平台限频

| 维度                  | `qqbot`               | 平台规则                                      |
| --------------------- | --------------------- | --------------------------------------------- |
| 同一子频道最小间隔    | 1 秒                  | 每秒最多 5 条                                 |
| 同一子频道每分钟      | 30 条                 |                                               |
| 账号级突发            | 5 条, 每秒补 1 个令牌 |                                               |
| 账号级每分钟 / 每小时 | 120 / 3000 条         |                                               |
| 每天                  | 不设                  | 主动消息每个子频道 20 条, 每个频道 2 个子频道 |
| 抖动                  | 无                    |                                               |
| 单条长度              | 2000 字符             | 需复核                                        |

## 5. 鉴权与签名

- access_token: `POST https://api.bot.qq.com/app/getAppAccessToken`, 有效期 7200 秒, 剩余不足 120 秒时刷新, 鉴权失败时丢弃重取; 调用头 `Authorization: QQBot <token>`
- 回调签名: Bot Secret 重复拼接到 32 字节作 Ed25519 种子; 校验 `X-Signature-Ed25519` (十六进制) 覆盖 `X-Signature-Timestamp + body`; 验签失败回 401
- 回调验证 (op 13): 签 `event_ts + plain_token` 回 `{plain_token, signature}`; 事件处理完回 `{"op": 12, "d": 0}`

## 6. 错误分类

| 情况                   | 业务码 / HTTP                                                             | 处理                                    |
| ---------------------- | ------------------------------------------------------------------------- | --------------------------------------- |
| 平台限频, 主动配额用完 | 20028, 304035, 304045, 304047, 304049, 304050, 1100100, 1100308, HTTP 429 | 重试, 60 秒后, 计入熔断                 |
| 安全打击, 机器人封禁   | 11254, 11265, 304025, 1100101, 1100103, 3300006                           | 失败, 计为风控                          |
| 鉴权                   | 11241 到 11275 中的 token 与 appid 错误, HTTP 401                         | 失败, 丢弃 token                        |
| 被动回复过期或不可回复 | 304026, 304027, 304028, 40034005                                          | 失败 `reply_window_expired`             |
| 等待人工审核           | 304023, 304024                                                            | 记为已发, 消息 id 用 `audit:<审核单号>` |
| 机器人未连网关, 5xx    | 304018, HTTP 5xx                                                          | 重试                                    |
| 超时                   |                                                                           | `unknown`, 不自动重发                   |

## 7. 与路由层的接口

- 声明: `server/contract/builtin.py` 的 `QQBOT`
- provider: `server/router/providers/qqbot.py`; 实现在 `server/router/providers/impl/qqbot/`
- 回调端点: `api/impl/router/ingress/ingress_qqbot.py`, 同步验签后在线程里入库并唤醒订阅
- 网关: `gateway/providers.py` 按实例类型 `qqbot` 构建 provider 与 `qqbot` 整形档

## 8. 需复核

- 官方文档 "发送消息接口要求机器人接口需要连接到 websocket 上保持在线状态" 是否适用于 webhook 模式; 如适用, 需要另起网关连接 (304018 会以可重试错误出现)
- 单条文本长度上限
- 私域机器人同一条消息是否同时推送 `AT_MESSAGE_CREATE` 与 `MESSAGE_CREATE` (当前靠去重键吸收)
- 事件回包是否必须是 `{"op": 12}` 的确切形状
