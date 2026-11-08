# QQ 空间接入: 说说与评论 (NapCat 实例上的第二条通道)

本文描述 QQ 空间 (Qzone) 在消息路由里的接入方式: 读哪些对象, 怎么拿登录态, 地址与 envelope 怎么映射, 风控档位与轮询节奏, 以及哪些地方还要复核

QQ 空间没有 OneBot 标准接口, NapCat 也不提供评论接口, 所以读写都走空间网页 CGI. 它和 `docs/providers/qq-napcat.md` 的聊天通道是同一个 QQ 账号, 同一个实例, 但接口不同, 风控也分开计数, 因此有自己的能力声明与限流档

决策记录: `.agents/notes/implemented/feature/2026-11-09-qzone-provider.md`

## 1. 范围

- 读: 关注的空间里最新的说说, 说说下的评论与二级回复
- 写: 在一条说说下发一级评论, 或回复其中某条评论
- 不做: 发说说, 删说说, 点赞, 转发, 读访客与相册; 不读陌生人空间 (只读配置里列出的空间, 最多 5 个)

## 2. 登录态与签名

- 不另外扫码, 不保存密码: 调用同一实例 NapCat 的 `get_cookies`, 参数 `domain=user.qzone.qq.com`, 拿到带 `p_skey` 的 cookie
- `g_tk` 由 `p_skey` 计算: 初值 5381, 对每个字符 `h += (h << 5) + ord(c)`, 结果取低 31 位
- cookie 只在进程内存里缓存 30 分钟; 接口返回登录态失效 (-3000, -4001) 时立即丢弃, 下次重新向 NapCat 取
- NapCat 掉线时 `get_cookies` 拿不到 `p_skey`, 轮询与发送都以 `provider_auth` 失败, 不会自己去登录

## 3. 地址与 envelope

| v2 地址                              | v1 存储键                           | 说明                                                   |
| ------------------------------------ | ----------------------------------- | ------------------------------------------------------ |
| `qq:<iid>/qzone/<主人QQ>`            | 无 (只作分组)                       | 选择器: 该空间全部说说                                 |
| `qq:<iid>/qzone/<主人QQ>/post/<tid>` | `qq:<iid>:qzonepost:<主人QQ>_<tid>` | 一条说说; 说说本身, 评论, 二级回复都是这个会话里的消息 |

| 对象     | `platform_message_id`                        | `kind`    | `reply_to`           |
| -------- | -------------------------------------------- | --------- | -------------------- |
| 说说     | `qzp:<tid>`                                  | `post`    | 空                   |
| 评论     | `qzc:<tid>:<评论序号>:<评论者QQ>`            | `comment` | `qzp:<tid>`          |
| 二级回复 | `qzr:<tid>:<评论序号>:<回复序号>:<回复者QQ>` | `comment` | 所在评论的 `qzc:` id |

- 消息 id 里带上回复时要用的评论序号与评论者, 发送侧不必查库; `dedup_key` 等于消息 id
- 正文里的 `@{uin:123,nick:某人,who:1}` 换成 `@某人`, 记进 `mentions`; 提到本号即 `mention_self`
- `reply_to_self`: 评论落在本号的说说下, 或二级回复落在本号的评论下; 本号自己发的消息三个信号里只有 `from_self` 为 true
- 带图的说说在正文末尾加 `[image xN]` 占位, 转发的说说把原文接在 `// 转发:` 之后, 图片本身不下载
- 时间取接口里的 Unix 秒, 转成 UTC `Z`

## 4. 风控档位

QQ 空间在能力声明里是 `risk_level=unofficial_web`, `rate_profile=qzone`, 比聊天的 `third_party` 更高一档: 网页接口对程序化访问更敏感, 节流时直接返回 -10000. 出站走独立的整形桶, 聊天与空间互不占用配额

| 维度                       | `qzone` (默认)            | `qzone_conservative` (实例 `rate_profile=conservative`) |
| -------------------------- | ------------------------- | ------------------------------------------------------- |
| 同一条说说两次评论最小间隔 | 60 秒                     | 180 秒                                                  |
| 账号级突发                 | 1 条, 每 60 秒补 1 个令牌 | 1 条, 每 180 秒补 1 个令牌                              |
| 账号级每分钟               | 2 条                      | 1 条                                                    |
| 账号级每小时               | 10 条                     | 5 条                                                    |
| 账号级每天 (Asia/Shanghai) | 30 条                     | 15 条                                                   |
| 同一段文字评到另一条说说   | 间隔 300 秒               | 间隔 900 秒                                             |
| 随机抖动                   | 3 到 8 秒                 | 5 到 15 秒                                              |
| 单条长度                   | 500 字符                  | 500 字符                                                |

- 全部是本项目的保守经验值, 不是腾讯公布的阈值, 只允许往更严的方向调
- 节流 (-10000) 与含 "频繁, 风控, 验证码, 安全验证, 异常, 限制" 的失败计为风控类失败, 喂给规格 9.3 的熔断; 熔断是按实例的, 所以空间的风控会同时停掉聊天出站, 这是有意往保守方向取
- 评论超时记为 `unknown`, 不自动重发 (评论可能已经发出); 连接失败与 5xx 可重试

## 5. 轮询

- 空间没有推送, 由一个守护线程轮询; 实例配置 `qzone_watch` (逗号分隔的 QQ 号, 可写 `self`, 最多 5 个) 为空时不发任何请求, 线程每 10 分钟醒一次看配置
- 只轮询状态为 online 的实例; 间隔 `qzone_poll_minutes`, 默认 10 分钟, 下限 5 分钟, 叠加 ±20% 抖动
- 每次每个空间读最新 10 条说说, 每条带最新 20 条评论; 已入库的由去重键吸收
- 遇到节流, 风控或登录失效, 本轮停止, 间隔翻倍, 最多 60 分钟; 成功一次恢复原间隔
- 配置方式: `PUT /api/v1/messaging/instances/{id}/config` 写入 `{"qzone_watch": "self", "qzone_poll_minutes": "10"}`

## 6. 与路由层的接口

- 地址声明在 `server/contract/builtin.py` 的 QQ 平台下 (`qzone`, `post` 两个 kind), 发送动作 `message_send` 的 target 增加 `post`
- provider: `server/router/providers/qzone.py`; 网页客户端与映射在 `server/router/providers/impl/qzone/`
- 出站: 分发器按会话类型选 provider 与整形桶 (`gateway/providers.py` 的 `for_session`, `shaper_for`)
- 入站: `gateway/impl/qzone_poll.py` 调 provider 的 `poll`, 经与推送入站相同的 `store_envelopes` 入库并唤醒订阅

## 7. 需复核

- `emotion_cgi_msglist_v6` 在部分账号上稳定返回 -10000 (社区项目 onebot-qzone 2026-03 的实测), 这类账号需要改读 `feeds3_html_more` 的 HTML, 本次未实现; 复核方法是用测试小号连续 3 天观察轮询日志的错误码
- 发评论接口返回体里新评论的 id 字段名; 拿不到时消息 id 里的评论序号记为 `new`, 下一轮轮询会以真实序号再入库一条
- 回复二级回复时 `commentUin` 取二级回复者还是所在评论的作者
- 评论的实际长度上限
- NapCat `get_cookies` 对 `user.qzone.qq.com` 返回的 cookie 是否总带 `p_skey`, 以及 cookie 的有效期
