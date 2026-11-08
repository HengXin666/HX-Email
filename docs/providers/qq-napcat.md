# QQ 接入方案: NapCat (OneBot 11) provider

本文是 HX-Email 消息插件中 QQ 侧消息监听与发送的接入方案, 只描述设计与约束, 不含实现代码

本文建立在三份现有材料之上: `docs/messaging-plugins.md` 的 1.1 节与 2.6 节, `server/src/hx_email/server/messaging/onebot.py` 与 `engine.py`, 以及 `server/src/hx_email/api/impl/messaging/event_routes.py`

会话地址, 幂等, 重试, 限流与内存口径以 `docs/messaging-router.md` 为准, 本文只说明 QQ provider 如何实现这些契约, 两者冲突时以规格为准

凡标注 需复核 的内容都是本文写作时无法从仓库代码或可打开的公开页面直接确认的事实, 实现前必须逐条核对, 核对方法写在同一处

## 0. 需求边界

> QQ 空间 (说说与评论) 与本文共用同一个 NapCat 实例与账号, 但走空间网页接口, 风控档位独立, 见 `docs/providers/qq-zone.md`

- 不自研任何 QQ 通信协议, 只对接市面上现成且仍在维护的协议端项目
- 不使用任何 QQ 官方机器人渠道, 使用一个个人 QQ 号作为收发账号
- 第一优先级是账号稳定性: 接入本身不能把账号推向风控或封禁
- 第二优先级是内存占用, 部署机器希望常驻内存尽量小
- 第三优先级是 CPU 占用, 空闲时不允许出现持续偏高的 CPU 消耗

## 1. 现状盘点: 现有代码已经做了什么

### 1.1 已有能力

- `engine.py` 的 `QQEngineManager` 按实例拉起 `mlikiowa/napcat-docker:latest` 容器, 使用 Docker 默认 bridge 网络
- 启动前预写 `onebot11.json`: 一个 HTTP server (容器内 3000 端口) 用于下行 API, 一个 HTTP client 用于上行事件, 两者都使用 `messagePostFormat: array`
- 上行事件地址默认指向 bridge 网关的 `http://<gateway>:8000/api/v1/messaging/events/qq`
- 二维码由容器写入实例目录 `cache/qrcode.png`, 后端直接读文件代理成图片, 不依赖 WebUI 端口
- QQ 登录态挂载在实例目录 `data` 子目录 , 即容器内 `/app/.config/QQ`, 容器重建后复用
- 镜像拉取失败时按 `DOCKER_MIRRORS` 依次回退加速源, 也支持 `HX_EMAIL_NAPCAT_MIRROR` 环境变量
- Xvfb 先启动并等待 socket 就绪再 exec 官方 entrypoint, 规避官方镜像里 sleep 2 秒的竞态
- `onebot.py` 的 `OneBotAdapter` 已覆盖 `get_login_info`, `send_private_msg`, `send_group_msg`, 好友与群列表, 群历史与好友历史, 以及踢人, 禁言, 全体禁言, 退群
- `event_routes.py` 按 `X-Messaging-Token` 头查实例, 把消息事件转为 `MessagingMessage` 后直接 INSERT 入库, 并把实例状态置为 online

### 1.2 缺口与风险点

下表每一条都对应现有代码中的具体位置, 是本方案要补齐的内容

| 编号 | 位置                               | 现状                                                           | 影响                                                         |
| ---- | ---------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------ |
| G1   | `impl/events.py` 的 `ingest_event` | `chat_id = group_id or user_id`                                | 私聊对象 QQ 号与某个群号数值相同时会混成一个会话             |
| G2   | `onebot.py` 的 `list_messages`     | 先按群号查历史, 查不到再按好友查                               | 同一数值同时是群号和好友号时返回错误会话的历史               |
| G3   | `ingest_event`                     | 群临时会话被当成普通私聊, 丢失来源群号                         | 回复临时会话时无法带上 group_id, 发送会失败                  |
| G4   | `store.py` 的 `save_message`       | 纯 INSERT, 表上没有唯一约束                                    | NapCat 重投或回调超时重试会产生重复消息                      |
| G5   | `ingest_event`                     | `post_type` 不是 message 的事件全部丢弃                        | 心跳, 生命周期, 掉线通知都被忽略, 无法做掉线检测             |
| G6   | `event_routes.py`                  | 收到任意事件都把状态写成 online                                | 状态只会被动变好, 不会因为掉线变差                           |
| G7   | `onebot.py` 的 `send_message`      | 无速率限制, 无幂等键, 文本按字符串直接下发                     | 突发调用直接打到账号上; 字符串消息可能被按 CQ 码解析         |
| G8   | `engine.py` 的 `start`             | `-p {api_port}:3000` 绑定宿主所有网卡, `access_token` 可能为空 | OneBot API 可能暴露到公网, 任何人都能用该号发消息            |
| G9   | `engine.py`                        | 镜像使用 `latest` 标签                                         | 上游一次发布就可能改变行为, 出问题时无法回到上一个可用版本   |
| G10  | `engine.py`                        | 容器无 `--memory` 与 `--cpus` 限制                             | 单个实例异常膨胀会拖垮整机                                   |
| G11  | `engine.py` 的 `_ENGINES`          | 引擎注册表只在进程内存里                                       | 后端重启后不知道哪些容器在跑, 需要靠 docker inspect 重新发现 |
| G12  | `onebot.py` 的 `status`            | 每次查状态都发起一次 `get_login_info`                          | 前端轮询状态时会变成对协议端的持续轮询                       |
| G13  | `engine.py` 的 `start`             | 上行事件地址写死 8000 端口                                     | 后端换端口后事件静默丢失                                     |
| G14  | `registry.py` 的 QQ 描述           | 文案写的是 lagrange-python 进程内运行                          | 与实际的 NapCat 容器实现不一致, 会误导用户与后续开发         |

另有一处需复核: 现有路由只认 `X-Messaging-Token` 头, 而 `engine.py` 写给 NapCat HTTP client 的是 `token` 字段; NapCat 上报时是否会带出名为 `X-Messaging-Token` 的头, 需要用一次真实上报抓包确认, 若不会, 则事件鉴权需要改为校验 NapCat 实际携带的头 (常见实现是 `Authorization: Bearer` 或 `X-Signature` 的 HMAC 签名, 以 NapCat 文档与抓包结果为准) 后再定

## 2. 选型结论与理由

### 2.1 结论

- 主选: NapCat, 仓库 NapNeko/NapCatQQ, 以 OneBot 11 HTTP 方式对接
- 备选: Lagrange 系列, 即 LagrangeDev/Lagrange.Core 及其 OneBot 前端 Lagrange.OneBot
- 明确排除: go-cqhttp, 仓库 Mrs4s/go-cqhttp

### 2.2 为什么主选 NapCat

- 它驱动的是腾讯官方 NTQQ 桌面客户端本体, 收发包与签名由官方客户端完成, 协议层面与正常桌面登录一致, 被协议特征识别的概率在这几类方案里最低
- 协议版本跟随官方客户端更新, 不依赖第三方签名服务器, 少了一个单点故障
- 原生提供 OneBot 11 HTTP server 与 HTTP client, 现有 `onebot.py` 与 `engine.py` 已经按这一形态实现, 选它不需要推翻已有代码
- 提供官方 Docker 镜像, 与现有受管引擎模式一致
- 维护活跃度判断依据: GitHub 仓库 NapNeko/NapCatQQ 页面显示创建于 2024-03 且提交数已超过 5000; 第三方部署文章 (2026-09 到 2026-10 发布) 以 `mlikiowa/napcat-docker:v4.18.28` 实测; 社区框架文档 (海豹核心 QQ 接入页) 把 NapCat 列为仍在维护的 NTQQ 方案
- star 数, 最新发布版本号与发布日期属于未核实的公开数据, 需实现前复核, 复核方法是打开仓库 Releases 页面并记录最新稳定版标签与日期
- 代价: 它是完整的桌面客户端加 Xvfb, 内存明显高于纯协议实现, 见第 6 节

### 2.3 为什么 Lagrange 只做备选

- Lagrange.Core 是 C# 的 NTQQ 协议纯实现, 不跑官方客户端, 内存与 CPU 远低于 NapCat, 这是它作为备选的价值
- 它自己实现协议, 版本跟随与特征一致性依赖维护者跟进, 风控层面不如直接跑官方客户端稳
- 维护活跃度判断依据: LagrangeDev 组织仓库列表显示 Lagrange.Core 在 2026-09 仍有更新; 仓库 README 说明当前主分支是 V2, V1 已经 sunset
- 需实现前复核的关键点: Lagrange.OneBot 属于 V1 体系, V1 已 sunset; V2 体系主推的是 Lagrange.Milky, 使用 Milky 协议而不是 OneBot 11. 若备选落到 V2, 则需要新写一个 Milky 适配层而不是复用 OneBot 适配器, 这一点决定备选的真实成本
- 第三方实测文章提到 .NET 在 ARM32 上存在已知稳定性问题, 本项目若部署在 ARM 设备上, 备选方案需单独冒烟测试
- 切换条件: NapCat 连续 7 天无法登录或出现系统性风控, 或部署机内存低于 1 GiB 无法承载 NapCat 时, 才启用备选

### 2.4 为什么排除 go-cqhttp

- 作者在仓库 README 中明确声明: 因腾讯不断更新加密方案, 已无力继续维护, 并建议迁移到无头 NTQQ 方案 , 见 go-cqhttp issue 2471
- 它模拟的是 Android QQ 旧协议, 需要外部签名服务器, 与当前官方客户端特征不一致, 登录失败与冻结报告集中
- 社区框架文档已把 go-cqhttp 与 QSign 方案标为弃用并建议迁移
- 它在资源上确实最省 (仓库 README 自述关闭数据库时约 15 MB 内存) 但第一优先级是不封号, 省内存不能抵消协议特征风险

## 3. 接入拓扑

### 3.1 文字拓扑图

```
[个人 QQ 小号]
    |  扫码登录, 登录态存于实例目录 data/
    v
[NTQQ 客户端容器: NapCat, 每个 QQ 号一个容器, bridge 网络]
    |  上行: OneBot 11 HTTP client  -> POST 本服务事件回调
    |  下行: OneBot 11 HTTP server  <- 本服务调用 send_* / get_* 动作
    v
[本服务 QQNapCatProvider]
    |  事件归一化, session 地址构造, dedup_key 构造, 错误分类, 登录态机
    v
[路由层 MessagingRouter]
    |  落库与入站去重, 出站幂等与速率整形, 按 session 地址分发给 route
    v
[MCP / REST 消费者]
```

### 3.2 每一跳的方向与失败表现

| 跳                            | 方向                         | 正常表现                          | 失败表现                                                    | 本服务的处理                                                |
| ----------------------------- | ---------------------------- | --------------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------- |
| QQ 号 -> NapCat               | 腾讯服务器到容器内客户端     | 心跳事件按固定周期到达            | 被踢下线, 冻结, 网络断开; 心跳停止或收到下线通知            | 进入 offline 或 frozen 状态, 停止全部发送, 告警             |
| NapCat -> provider (上行事件) | 容器主动 POST 到后端         | 回调返回 2xx                      | 后端不可达时事件被 NapCat 丢弃, 不保证重投 (重投行为需复核) | 恢复后用 `get_*_msg_history` 按会话补拉最近 20 条并去重入库 |
| provider -> NapCat (下行 API) | 后端主动 POST 到容器发布端口 | 返回 `status: ok` 且 `retcode: 0` | 连接拒绝, 超时, 非零 retcode                                | 按第 5.5 节分类: 退避, 放弃或熔断                           |
| provider -> 路由层            | 进程内调用                   | 同步返回                          | 路由层抛错                                                  | 事件先落库再分发, 分发失败不影响落库                        |
| 路由层 -> 消费者              | REST 拉取或 MCP 调用         | 按游标增量读                      | 消费者掉线                                                  | 消息留在表中, 消费者回来后从游标续读, 不重放推送            |

### 3.3 网络约束

- OneBot HTTP server 的宿主端口只绑定 `127.0.0.1`, 即 `-p 127.0.0.1::3000` 由 Docker 分配随机端口, 修复 G8
- `access_token` 创建实例时强制生成 32 字节随机值, 不允许为空
- 上行事件地址的端口从后端实际监听配置读取, 不写死 8000, 修复 G13
- WebUI 不发布到宿主, 二维码继续走 cache 文件, 与现状一致

## 4. 会话标识方案

### 4.1 构造规则

QQ 会话使用规格第 2 节的统一 session 地址 `qq:<instance_id>:<session_type>:<peer>`, 由本服务构造, 写入 `messaging_messages.chat_id`

| 会话类型   | session_type | peer                  | 示例                       |
| ---------- | ------------ | --------------------- | -------------------------- |
| 好友私聊   | `private`    | 对方 QQ 号            | `qq:3:private:3000001`     |
| 群聊       | `group`      | 群号                  | `qq:3:group:600001`        |
| 群临时会话 | `temp`       | `<群号>-<对方 QQ 号>` | `qq:3:temp:600001-3000001` |

- `instance_id` 是 `messaging_instances.id`, 一个实例只登录一个 QQ 号, 当前登录号 (OneBot 事件的 `self_id`, 下行时 `get_login_info` 的 `user_id`) 记录在实例状态里, 不进入地址
- 私聊事件的 `sub_type` 为 `friend` 时归入 `private`, 为 `group` 时归入 `temp`; 临时会话的来源群号在 NapCat 上报中的具体字段位置需复核, 复核方法是用测试小号从群里发起一次临时会话并抓取原始上报
- 反向解析规则以规格第 2 节为准: 第 3 段决定调用 `send_private_msg` 还是 `send_group_msg`, `temp` 类会话下发时同时带 `user_id` 与 `group_id`

### 4.2 为什么必须由本服务构造

- QQ 号与群号是两套独立编号, 数值可以相同; 直接用平台 id 就是 G1 与 G2 的根因, 地址第 3 段把它们分开
- 同一部署可能挂多个 QQ 号, 同一个群被两个号同时加入时, 两个号看到的是两个独立会话; 每个号对应一个独立实例, `instance_id` 已足够区分
- 临时会话的回复必须携带来源群号, 平台 id 本身不含这个信息, 所以 `temp` 的 peer 同时含群号与对方 QQ 号
- 统一抽象层要覆盖 GitHub, Telegram 与 Discord, 所有平台共用 `<platform>:<instance_id>:<session_type>:<peer>` 结构, 消费者看到地址就能判断平台
- 协议端从 NapCat 换成备用实现时实例行不变, 地址也不变, 历史会话与 MCP 侧引用都不受影响

### 4.3 迁移现有数据

- 现有 `messaging_messages` 中的 chat_id 是裸数字 (`impl/events.py` 取 `group_id or user_id`), 迁移时用 `chat_type` 与 `raw_json` 中的 `group_id`, `user_id`, `sub_type` 重算为 session 地址, 实例号取该行的 `instance_id`
- 无法从 raw_json 判定会话类型的旧行保持原值不改, 并在迁移报告中计数, 路由层把解析失败的 chat_id 视为不可寻址, 不出现在 `sessions_list` 中

## 5. 防封与稳定性

本节的数值是本项目的保守取值, 腾讯不公开风控阈值, 这些数值不是腾讯给出的安全线; 上线后以测试小号 14 天运行记录为依据再调整, 只允许往更保守的方向调整, 放宽必须有记录支撑

### 5.1 账号策略

- 只使用专用小号, 禁止使用主号, 前端创建实例时显示这条约束并要求勾选确认
- 小号建议实名, 绑定手机, 已正常使用 30 天以上, 有正常好友与群关系; 新注册号直接挂机器人风险明显更高
- 登录地固定: 一个小号只在一台部署机上登录, 不在多个地域之间来回迁移; 部署机更换 IP 所在城市时, 先在新机器上手动扫码并静置 24 小时不发消息
- 同一部署机上同时在线的 QQ 号不超过 3 个, 避免同一出口 IP 下出现多个号的批量行为
- 不在同一个号上同时运行手机 QQ 以外的其他第三方协议端

### 5.2 发送速率整形

速率整形由路由层的令牌桶统一实现, 参数与依据以规格第 9.1 节为准, QQ provider 不另设限流; 下表是 `rate_profile=default` 的取值, 全部是本项目经验值, 不是腾讯公布的阈值

| 维度         | 上限                        | 说明                                                                                                                      |
| ------------ | --------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 同一 session | 最小间隔 3 秒, 每分钟 10 条 | 防止对单个人或单个群刷屏                                                                                                  |
| 账号级突发   | 3 条, 之后每秒补 1 个令牌   | 允许 3 条以内的瞬时突发                                                                                                   |
| 账号级每分钟 | 20 条                       | 滑动窗口计数                                                                                                              |
| 账号级每小时 | 300 条                      | 滑动窗口计数                                                                                                              |
| 账号级每天   | 1000 条                     | 自然日按 Asia/Shanghai 计                                                                                                 |
| 随机抖动     | 每次 0.5 到 1.5 秒          | 打散固定节奏                                                                                                              |
| 单条长度     | 1500 个字符                 | 超出返回 `text_too_long`, 不拆条; QQ 客户端实际上限需复核, 复核方法是用测试小号发送 1500, 3000, 4500 字符纯文本并记录结果 |

- `conservative` 档见规格第 9.1 节
- 超出限额的消息在 outbox 中排队, 接口在 `wait_seconds` 内无法投递时返回 `rate_limited` 与 `queued_until`, 消息不丢
- 同一内容发往多个会话 (去除空白后 SHA-256 相同) 额外受限: 相邻两个会话间隔不少于 8 秒再叠加 0 到 4 秒随机抖动, 同一内容每天最多发往 20 个会话
- 路由层不提供批量群发接口, 上面的规则针对调用方逐条调用 `message_send` 形成的事实群发

### 5.3 消息格式

- 下行一律使用 OneBot 消息段数组 `[{"type": "text", "data": {"text": ...}}]`, 不再传裸字符串, 避免文本中的 `[CQ:...]` 被当成 CQ 码解析, 修复 G7 的后半部分
- 第一阶段只发纯文本与回复引用, 不发图片, 文件, 语音, 不发 @全体成员

### 5.4 幂等与去重

本节是规格第 7.2 节到第 7.5 节在 QQ 上的落点, 规则以规格为准

- 下行幂等: 调用方在 `message_send` 中传 `idempotency_key` (8 到 64 字符, 推荐 UUID v4), 路由层以 `(instance_id, idempotency_key)` 为唯一键, 幂等窗口 7 天; 窗口内重复提交返回第一次的 `delivery_id` 与当前状态, 并带 `deduplicated=true`
- OneBot 11 没有平台侧幂等键, 因此下行发送超时属于结果未知: 状态记为 `unknown`, 不自动重发, 由调用方决定是否用新的 `idempotency_key` 再发; 进程在调用期间退出时同样记为 `unknown`; 只有连接被拒绝这种确定没发出去的错误才按第 5.5 节自动重试
- 上行去重键: `(instance_id, dedup_key)`, 其中 `dedup_key = "qq:<message_id>:<time>"`, `time` 取 OneBot 事件的 Unix 秒; 在 `messaging_messages` 上建永久唯一索引, 入库用 `INSERT ... ON CONFLICT DO NOTHING`, 修复 G4
- NapCat 的 `message_id` 是否在容器重启后会重复使用需复核; 即使复用, 不同时间的新消息因 `time` 不同不会被误判为重复, 而同一事件的重投两者都相同会被吸收, 这样不需要时间窗口, SQLite 的永久唯一索引就能表达
- 旧消息由规格第 10 节的保留期清理删除, 默认 90 天
- 补拉历史 (第 3.2 节) 产生的记录走同一套上行去重

### 5.5 失败分类与退避

| 类别       | 判定依据                                                                     | 处理                                                                                             |
| ---------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| 可退避     | 连接被拒绝; HTTP 502, 503, 504; 容器正在重启                                 | 指数退避 2 秒, 4 秒, 8 秒, 单次上限 60 秒, 叠加 20% 随机抖动, 最多重试 3 次, 与规格第 7.4 节一致 |
| 结果未知   | 请求超时 (默认 10 秒)                                                        | 不重试, 状态 `unknown`, 写入告警日志                                                             |
| 直接放弃   | retcode 1400 即参数错误, 1404 即动作不存在; 目标不是好友或已不在群内; 被禁言 | 不重试, 返回 `failed` 与错误码                                                                   |
| 放弃并告警 | HTTP 401, 403 或 retcode 1401, 1403 (token 不匹配)                           | 不重试, 实例标记 `error`, 通知用户检查配置                                                       |
| 熔断       | 返回文案含风控, 频繁, 账号异常, 冻结等字样; 收到下线或冻结通知               | 立即暂停该实例全部发送, 见下                                                                     |

- retcode 1400, 1401, 1403, 1404 是 OneBot 11 标准约定; NapCat 自定义的失败码与风控文案关键字需复核, 复核方法是汇总测试期 NapCat 日志中所有非零 retcode 及 `wording` 字段
- 熔断由路由层执行, 规则以规格第 9.3 节为准: 5 分钟内出现 3 次风控类失败或收到冻结与下线通知, 出站进入 `held` 30 分钟; 当天第二次 6 小时; 当天第三次进入 `manual_hold`, 只能由用户在前端手动解除
- QQ provider 只负责分类: 风控类失败在 `SendResult` 中置 `risk_signal=true`
- 熔断期间接收照常, 只停发送; 熔断与解除都写入实例事件并推送给消费者

### 5.6 登录态维持

- 掉线检测以事件驱动为主: NapCat 的 OneBot 心跳 `meta_event.heartbeat` 周期设为 30 秒, 配置项名称需复核; 连续 90 秒没有收到任何事件时, 主动调用一次 `get_status`, 连续 2 次失败或返回不在线即判定 offline
- 显式下线通知 (被踢, 冻结, 在其他设备登录) 直接判定 offline 或 frozen, 不等心跳超时; NapCat 对应的事件类型名需复核
- 重连退避: 判定 offline 后按 1 分钟, 5 分钟, 15 分钟, 60 分钟重启容器尝试用已保存登录态快速登录, 24 小时内最多 4 次; 4 次都失败后停止自动重连并等待用户处理
- 状态为 frozen (冻结或安全验证) 时一律不自动重连, 因为反复重连会加重风控
- 二维码过期处理: 有效期以客户端实际行为为准且需复核, 现有 `create_login` 按 300 秒返回; 一次登录流程中自动刷新二维码最多 5 次, 超过后停止生成, 前端显示 重新开始登录 按钮, 避免无人值守时反复生成二维码
- 容器重启策略使用 `--restart on-failure:3`, 不使用 `always`, 防止客户端崩溃时无限重启造成高频登录

### 5.7 明确不做的事

- 不做营销群发, 不做广告投放, 不做批量拉群
- 不主动加好友, 不自动通过好友申请, 不自动通过入群申请
- 不主动私聊陌生人; 私聊只发往已是好友的对象, 或在临时会话中回复对方先发起的消息
- 不自动点赞, 不刷戳一戳, 不自动修改资料与头像
- 不抓取群成员列表做外部用途, 群成员信息只在群管理操作时按需读取并缓存 6 小时
- 不在同一个号上运行多个协议端

## 6. 内存与 CPU

### 6.1 量级

- NapCat 运行的是完整 NTQQ 桌面客户端加 Xvfb, 一个 QQ 号就是一组常驻进程
- 可查证的第三方数据: 一篇 2026-10 发布的实测文章记录 x86_64 机器上 NapCat 加 AstrBot 空闲时约 855 MiB 内存, 93 个进程; 其中 AstrBot 单独约 323 MiB, 由此推算 NapCat 部分约 500 MiB 量级, 该推算未经本项目验证
- NapCat issue 556 记录约 400 个群的号运行一段时间后内存升到 800 MB 以上, 说明群数量与群成员缓存会显著拉高内存
- 对照: go-cqhttp README 自述约 15 MB, Lagrange.Core 作为纯协议实现也在百 MB 以下量级但需实测, 这是备选方案存在的理由
- 本项目自己的数值需实测, 测量方法见 6.3

### 6.2 降低内存的手段

- 容器硬限制: `--memory=1g --memory-swap=1g --cpus=1`, 与 ADR 0005 的验收项 A5 一致, 修复 G10; 1g 约为第 6.4 节 p95 目标 700 MiB 的 1.4 倍, 实测后改为实测 p95 的 1.5 倍且不低于 1g; 上限不能压到 p95 附近, 因为触顶会被 OOM 杀掉, 容器重启后要重新登录, 频繁重新登录会抬高风控风险
- 单容器多号复用: NTQQ 一个客户端进程只承载一个账号, 多号仍然是多组进程; NapCat 是否支持一个容器内多个账号进程需复核; 可落实的复用是所有实例共用同一镜像只读层与共享库页缓存, 以及固定同一个镜像版本, 不要让不同实例跑不同版本导致页缓存无法共享
- 闲置实例自动休眠: 只对用户标记为 仅发送 的实例生效; 连续 24 小时没有任何发送请求时停止容器, 下一次发送请求到来时用保存的登录态拉起; 每个实例每天最多唤醒 4 次, 超过则保持常驻; 需要接收消息的实例不休眠, 因为休眠期间的消息无法上报
- 事件驱动不做轮询: 状态由心跳与上报事件维护, `status()` 读本地状态机而不是每次调用 `get_login_info`, 修复 G12; 前端轮询状态只读数据库
- 消息表增量读: REST 与 MCP 读消息一律按规格第 7.1 节的 cursor 增量读, 走 `(instance_id, chat_id, id)` 索引, 每次最多返回 200 条, 不做全表扫描, 不把历史消息常驻内存
- 群成员信息只在群管理操作时按需拉取, 结果缓存 6 小时, 不全量预加载, 针对 issue 556 的内存增长点
- 关闭 NapCat 的 debug 输出与不用的网络端点 ; 现有配置已经关闭 websocket 与 SSE, 保持现状
- Xvfb 保持当前 16 位色深, 不提高分辨率

### 6.3 测量方法

- 内存: 登录成功后静置 10 分钟作为基线, 之后每 60 秒采样一次 `docker stats --no-stream --format '{{.MemUsage}}' hx-messaging-<实例id>`, 同时读取容器 cgroup 的 `memory.current`, 连续 24 小时; 报告 p50, p95, 最大值, 以及群数量与好友数量
- CPU: 同一采样序列中记录 `docker stats` 的 CPU 百分比; 空闲定义为过去 10 分钟内没有收发消息
- 本服务侧: 用 `ps -o rss,pcpu -p <后端 pid>` 每 60 秒采样, 对比启用与未启用 QQ 实例两种情况
- 测试账号规模固定为 20 个群, 50 个好友, 以便前后版本可比

### 6.4 目标值

| 对象                 | 指标                  | 目标                                                          |
| -------------------- | --------------------- | ------------------------------------------------------------- |
| NapCat 容器          | 空闲 CPU, 10 分钟平均 | 不超过单核的 2%                                               |
| NapCat 容器          | 24 小时内存 p95       | 不超过 700 MiB (以 20 个群的测试号为准, 初始目标, 实测后修订) |
| 本服务 provider 部分 | 空闲 CPU, 10 分钟平均 | 不超过单核的 0.5%, 且没有任何定时轮询                         |
| 本服务 provider 部分 | 每个实例额外内存      | 不超过 20 MiB                                                 |

## 7. 与路由层的接口契约

### 7.1 类型定义

QQ provider 实现 ADR 0005 第 4 节的 `MessagingProvider` 协议, `SessionRef`, `OutboundPayload`, `SendResult`, `ProviderLimits` 以 ADR 为准, 本节只补充 QQ 专有的类型

```python
from dataclasses import dataclass, field
from typing import Literal, Mapping, Callable, Protocol

QQSessionType = Literal["private", "group", "temp"]
LoginPhase = Literal["stopped", "starting", "awaiting_scan", "online", "offline", "frozen", "error"]
Transport = Literal["ok", "timeout", "connect_error", "http_error"]


@dataclass(frozen=True)
class QQSession:
    address: str            # qq:<instance_id>:<session_type>:<peer>
    instance_id: int
    session_type: QQSessionType
    peer_user_id: str = ""  # private, temp
    peer_group_id: str = ""  # group, temp


@dataclass(frozen=True)
class OneBotCallResult:
    transport: Transport
    http_status: int = 0
    retcode: int = 0
    wording: str = ""
    data: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderHealth:
    phase: LoginPhase
    self_id: str
    last_event_at: str      # ISO 8601 UTC, Z 结尾
    sent_last_minute: int
    sent_today: int


@dataclass(frozen=True)
class ProviderEvent:
    event_id: str           # 本服务生成的 UUID
    instance_id: int
    type: Literal[
        "message.received",
        "message.recalled",
        "login.changed",
    ]
    occurred_at: str        # ISO 8601 UTC, Z 结尾
    session: str = ""
    payload: Mapping[str, object] = field(default_factory=dict)


EventSink = Callable[[ProviderEvent], None]
```

- `OneBotCallResult` 是 `OneBotAdapter` 新增公开方法 `call_action(action, params)` 的返回值, 它不抛业务异常, 把现有 `_call` 里被统一包成 `MessagingError` 文案的超时, 连接错误, HTTP 状态与 retcode 分开交出来, 见规格第 9.5 节
- 熔断的打开与关闭, 发送计数都由路由层维护并写入实例事件, 不再由 provider 发出 `risk.*` 与 `message.sent` 事件

### 7.2 provider 必须实现的方法

```python
class QQNapCatProvider(Protocol):
    platform: Literal["qq"]

    # MessagingProvider 协议, 签名以 ADR 0005 第 4 节为准
    def list_sessions(self, instance_id: int) -> list[SessionRef]: ...
    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult: ...
    def parse_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> list[dict[str, object]]: ...
    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool: ...

    # QQ 专有
    def resolve_session(self, address: str) -> QQSession: ...
    def health(self, instance_id: int) -> ProviderHealth: ...
    def backfill(self, address: str, limit: int = 20) -> list[dict[str, object]]: ...
    def subscribe(self, sink: EventSink) -> None: ...
```

- 登录, 二维码, 群管理沿用现有 `OneBotAdapter` 与 `/api/v1/messaging` 路由, 不进入 provider 协议
- 现有 `MessagingAdapter.send_message(target, text) -> str` 保留给旧前端路径, 但其 REST 入口 `POST /api/v1/messaging/instances/{id}/send` 改为调用 `facade.send`, 由服务端生成 `idempotency_key`, 与 MCP 共享整形与幂等
- `send` 只做 provider 的部分, 顺序固定: 解析 session, 把 `text` 与 `reply_to` 组装成 OneBot 消息段数组, 调用 `call_action`, 按第 5.5 节分类成 `SendResult`; 幂等检查, 熔断检查, 令牌桶与出站记录由路由层在调用 `send` 之前和之后完成
- 分类规则: `transport=timeout` 为 `status="unknown"`; `connect_error` 与 HTTP 502, 503, 504 为 `status="retry"`; retcode 1400, 1404, 目标不存在, 被禁言为 `status="failed"`; HTTP 401, 403 与 retcode 1401, 1403 为 `failed` 并把实例标记 `error`; `wording` 含风控类文案时为 `failed` 且 `risk_signal=true`
- `parse_event` 产出的 envelope 必须带 `session`, `dedup_key` 与 ISO 8601 UTC 的 `occurred_at`, 事件先落库再交给 sink, sink 抛错只记日志, 不回滚落库

### 7.3 事件结构示例

```json
{
  "event_id": "5b1f0c8e-6a1d-4f2e-9a57-2f0d7e8b4c11",
  "instance_id": 3,
  "type": "message.received",
  "occurred_at": "2026-11-02T14:05:00Z",
  "session": "qq:3:group:600001",
  "payload": {
    "platform_message_id": "1838273",
    "dedup_key": "qq:1838273:1793628300",
    "sender_id": "3000001",
    "sender_name": "测试成员",
    "text": "你好",
    "segments": [{ "type": "text", "data": { "text": "你好" } }],
    "reply_to": ""
  }
}
```

- `login.changed` 的 payload 为 `{"from": <LoginPhase>, "to": <LoginPhase>, "reason": <字符串>}`
- 熔断状态由路由层写入实例事件, 消费者在 `sources_list` 的 `outbound` 与 `held_until` 中读取

## 8. 分阶段落地

### 阶段一: 修正现有链路, 做到可用

- 范围: G1, G3, G4, G7, G8, G9, G13, G14; session 地址新规则与数据迁移; 上行 dedup_key 唯一索引; 下行改为消息段数组; OneBot 端口只绑 127.0.0.1 且 token 必填; 镜像固定到一个已验证的具体版本标签; 事件鉴权头按抓包结果确认
- 里程碑: 用测试小号完成扫码登录; 同一事件重复 POST 两次只入库一次; 私聊对象号码与群号相同时形成两个不同会话; 回复群临时会话成功; 宿主机外网扫描不到 OneBot 端口

### 阶段二: 防封与稳定性

- 范围: 第 5 节全部内容, 包括路由层令牌桶的 QQ 参数, 事实群发限制, 幂等键, 失败分类, 熔断, 心跳掉线检测, 重连退避, 二维码刷新上限; G5, G6, G12
- 里程碑: 连续发送 100 条到 5 个会话, 无重复, 无超速; 第 21 条每分钟请求返回 `rate_limited`; 手动 `docker stop` 容器后 90 秒内状态变为 offline; 恢复后补拉历史无重复; 测试小号连续运行 14 天无风控提示

### 阶段三: 资源收敛

- 范围: 第 6 节的容器限制, 闲置休眠, 增量读游标, 群成员缓存; G10, G11; 启动时用 `docker ps --filter name=hx-messaging-` 重建引擎注册表
- 里程碑: 产出一份 24 小时测量报告, NapCat 空闲 CPU 与内存 p95 达到第 6.4 节目标或给出偏差原因; 后端重启后不需要重新扫码即可恢复所有在线实例

### 阶段四: 备选与扩展

- 范围: 撤回事件, 回复引用的完整展示; 对 Lagrange V2 (Milky) 做一次接入可行性验证, 只验证登录, 收消息, 发文本三项
- 里程碑: 撤回事件以 `message.recalled` 出现在消费者侧; 备选验证报告写明 Lagrange 方案的内存实测值与切换成本, 由用户决定是否纳入正式支持

## 9. 实现前复核清单

- NapCat 当前稳定版本号与发布日期, 以及要固定的镜像标签
- NapCat 上行事件实际携带的鉴权头名称
- 群临时会话来源群号在上报中的字段位置
- NapCat 心跳周期配置项名称, 以及被踢下线与冻结对应的事件类型
- NapCat 自定义失败码与风控类 `wording` 文案
- NapCat `message_id` 在容器重启后是否会重复
- 后端不可达时 NapCat HTTP client 是否重投事件
- 二维码实际有效期
- NapCat 是否支持一个容器内承载多个账号
- Lagrange.OneBot 与 Lagrange.Milky 的当前维护状态, 以及 Lagrange 方案实际内存占用
