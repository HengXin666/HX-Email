# Agent Note: QQ 空间作为 QQ 平台下的独立风控通道, 轮询读取, 网页接口评论

Status: implemented

Decision-ID: qzone-provider

## Code

- `server/src/hx_email/server/router/providers/qzone.py`
- `server/src/hx_email/server/router/providers/impl/qzone/qzone_events.py`
- `server/src/hx_email/server/gateway/impl/qzone_poll.py`

## Problem

需求要求覆盖 QQ 空间 (说说与评论), 而路由层只有 QQ 私聊, 群与临时会话:

1. QQ 空间没有 OneBot 标准接口, NapCat 也没有评论接口, 不能复用 `send_msg` 路径.
2. 空间是 "主人 / 说说 / 评论" 多层对象, 契约 v2 的地址层级与 capabilities 已经能表达, 但没有声明.
3. 网页接口的风控与聊天不同, 而整形器与能力声明都只有一个平台级档位, 无法让同一个账号在两条通道上用不同的限流.
4. 空间没有推送, 现有入站全部是 webhook, 没有拉取循环.

## Decision

- 地址: QQ 平台下新增 `qzone` (分组层, id 为主人 QQ 号) 与 `post` (一条说说, 存储键 `qq:<iid>:qzonepost:<主人>_<tid>`); 评论与二级回复都是说说会话里的消息, 消息 id 自带回复所需的评论序号与作者.
- 能力声明: `AddressKind` 增加 `risk_level` 与 `rate_profile`, 平台增加默认 `rate_profile`; capabilities 输出每个层级的风控等级与档位. 空间为 `unofficial_web` / `qzone`, 聊天 `third_party` / `qq`, GitHub `official` / `github`.
- 风控档位: 新增 `QZONE_DEFAULT` 与 `QZONE_CONSERVATIVE`, 比聊天 conservative 更严; 网关多一个进程级整形桶 `QZONE_SHAPER`, 分发器按会话类型选桶与 provider.
- 登录态: 用同一实例 NapCat 的 `get_cookies` 取空间 cookie, 由 `p_skey` 算 `g_tk`, 只缓存在内存.
- 入站: 一个守护线程按实例配置 `qzone_watch` 轮询, 间隔下限 5 分钟加抖动, 节流与风控翻倍退避; 入库复用 `store_envelopes`, 订阅照常被唤醒.
- 触发信号由 provider 计算: 解析空间的 `@{uin:..}` 写 mentions; 评论落在本号说说下, 回复落在本号评论下为 `reply_to_self`.

## Alternatives considered

- 什么都不做, 继续只支持聊天: 最强理由是网页接口没有官方文档, 维护成本与风控风险都高. 否决: 需求明确要 QQ 空间与评论, 而且契约 v2 已经为它留了地址层级.
- 复用现有聊天通道, 让 `QQNapCatProvider` 顺带处理空间: 最强理由是同一账号同一实例, 改动最少. 否决: 聊天的整形桶与限流数值会被直接套到网页接口上, 空间评论还会挤占聊天配额; 风控等级也无法区分.
- 把空间做成独立平台与独立实例 (`qzone:<iid>`): 最强理由是平台级的风控与熔断天然隔离. 否决: 网关要求实例类型与地址平台一致, 空间又必须借用 QQ 实例的登录态, 独立实例需要新建实例流程与跨实例引用, 而且同一账号被拆成两个实例违背 "一个实例一个账号" 的约定.
- 依赖第三方协议端扩展 (例如 onebot-qzone, NapCat 的发说说扩展): 最强理由是不用自己维护网页接口. 否决: 要多部署一个进程, 且这些扩展也只是同一套网页接口的封装, 覆盖不到评论回复.
- 读 `feeds3_html_more` 的 HTML 而不是 `emotion_cgi_msglist_v6`: 最强理由是社区实测部分账号上 msglist 返回 -10000. 暂不采纳: HTML 解析脆弱, 先用结构化 JSON, 遇到 -10000 按节流退避; 列入需复核.

## Consequences

- 空间的风控类失败计入按实例的熔断, 会同时停掉聊天出站; 这是往保守方向取的, 如需隔离要给熔断加通道维度.
- 发评论成功后, 若接口不返回新评论 id, 出站记录与下一轮轮询读到的同一条评论会各有一行.
- 轮询与分发两个线程共用一个空间客户端 (cookie 缓存与 requests.Session), 只做简单的读写, 未加锁.
- 没有用真实账号联调; 接口与字段取自社区资料, 复核项见 docs/providers/qq-zone.md 7.
