# Agent Note: 消息能力升级为路由网关, 适配器只做平台连接, 订阅与分发收敛到独立路由层

Status: implemented

Decision-ID: messaging-router-gateway

## Code

- `server/src/hx_email/server/messaging/types.py`
- `server/src/hx_email/server/router/provider.py`
- `server/src/hx_email/server/router/impl/outbox.py`
- `server/src/hx_email/server/router/providers/qq.py`
- `server/src/hx_email/api/impl/router/ingress/ingress_github.py`
- `server/src/hx_email/models/messaging.py`

## Problem

HX-Email 的消息插件已经能通过 NapCat 与 OneBot 11 收发 QQ 消息, 但它只是面向前端页面的一组 REST
用户这一轮把它重新定位为基建服务, 要求调用方可以选定某个平台账号下的某个会话, 监听其内容并向其发送内容
平台要能无限扩展, 首批是 QQ 与 GitHub, 之后覆盖微信, Telegram 与 X 这类论坛型平台
各平台的获取与发送要聚合成一个通用接口, 以 MCP 形式提供给 AI 调用与监听, 同时支持同步与异步
硬约束是不能因接入导致账号被封, 以及常驻内存小且 CPU 不长期处于高位

现有实现与这些要求之间有四个缺口
- `MessagingAdapter` 只有平台连接语义, 没有订阅与投递状态
- `messaging_messages` 没有去重约束, 平台重投会写出重复行
- 读取只有最新 n 条, 没有增量 cursor, 监听只能轮询
- 发送是同步直发, 没有速率整形与幂等键

## Decision

在同仓新增 `server/router/` 路由层, 统一使用 source, sink, route, envelope, cursor 五个概念; 实现规格 `docs/messaging-router.md` 是全套文档的唯一契约, ADR 与两份 provider 方案与它冲突时以规格为准
- 会话地址只有一套: `<platform>:<instance_id>:<session_type>:<peer>`, session_type 为 `private`, `group`, `temp`, `repo`, `issue`
- 适配器是平台连接, 路由层是订阅与分发, 适配器通过一个更窄的 `MessagingProvider` 协议成为路由层的 provider
- 依赖方向为 路由层 -> provider -> adapter, `server/messaging/` 不 import 路由层, 抽象基类 `MessagingAdapter` 的签名不改; 它的 `send_message(target, text) -> str` 给不出 `reply_to` 与错误分类, 所以 QQ provider 改用 `OneBotAdapter` 新增的结构化动作接口 `call_action`
- 对外以 MCP server 为主 (`/mcp` streamable HTTP 与 `hx-email mcp` stdio), REST 兼容面在 `/api/v1/router`, 与 MCP tool 一一对应
- 现有前端继续使用 `/api/v1/messaging`, 内部改为共享同一张消息表, 同一套 cursor 与同一个 outbox

同步与异步
- 同步路径是 send, list, fetch, 发送默认等待至多 5 秒拿到平台消息 ID, 超时返回 queued
- 异步路径是订阅加推送, MCP 用 resource 通知与长轮询 tool, 外部用 SSE 与签名 webhook
- 背压原则是通知可以丢, 数据不会丢, 每订阅者信号队列上限 256, 溢出标记 gap 由消费者按 cursor 补读

稳定性
- QQ 不做任何协议自研, 只用 NapCat 的 OneBot 11, Lagrange.OneBot 为同接口备用
- 每个 QQ 账号独立实例与独立容器, session 地址绑定唯一实例, 不做跨号切换发送
- 出站经过令牌桶整形, QQ 默认同会话 3 秒间隔且每分钟 10 条, 账号突发 3 条, 每分钟 20 条, 每小时 300 条, 每日 1000 条, 单条 1500 字符, 附加随机抖动, 均为本项目经验值
- 平台出站以 `(instance_id, idempotency_key)` 幂等, webhook 投递以 `(route_id, idempotency_key)` 幂等, 窗口 7 天; 超时等结果未知记为 `unknown` 不自动重发, QQ 与 GitHub 都没有平台侧幂等键, GitHub 用评论隐藏标记查重
- 入站以 `(instance_id, dedup_key)` 永久唯一键去重, QQ 的 dedup_key 含消息时间, 旧消息按保留期清理
- 平台出站可重试错误 2 秒起步翻倍最多重试 3 次, webhook 投递 10 秒起步翻倍单次上限 1 小时, 24 小时后 `dead`; 5 分钟内 3 次风控类失败触发该账号出站 `held` 30 分钟, 当天第三次进入 `manual_hold`

资源占用
- QQ 与 GitHub 都是平台推送, 路由层没有周期性拉取循环, 唯一常驻定时器是 60 秒一次的 housekeeping, 有 SSE 连接时每条另有 25 秒心跳
- 读取全部按 cursor 增量走索引, 大于 16 KB 的 raw 落盘, 信号队列只存 cursor 不存消息体
- 验收项写成可测量数字, 以 `router_enabled` 开关对照测增量: 空闲 CPU 增量不超过单核 0.5%, RSS 增量不超过 40 MB; NapCat 容器限制 1g 内存, 高于 700 MiB 的 p95 目标, 因为 OOM 被杀会重新登录并抬高风控风险

GitHub
- 使用 GitHub App, webhook 接收事件并以 `X-Hub-Signature-256` 校验, installation token 发评论与建 issue
- 回调路径为 `/api/v1/router/ingress/github/{instance_id}`, 订阅 `issue_comment`, `pull_request_review_comment`, `pull_request_review`, `issues`, `pull_request` 与默认投递的 installation 两类事件, 不订阅 `push`
- 权限最小集为 Metadata 只读, Issues 读写, Pull requests 读写, 不申请 Contents

完整论证见 `docs/adr/0005-messaging-router-gateway.md`, 实现规格见 `docs/messaging-router.md`

## Alternatives considered

- 什么都不做 / 复用现有 `/api/v1/messaging`: 最强理由是它已经能收发 QQ 消息, 有前端有测试, 零新增代码, AI 也能直接调 REST. 否决原因是没有 cursor 导致调用方只能反复拉最新 n 条, 没有订阅导致监听只能轮询而违背 CPU 目标, 没有整形与幂等会放大封号风险, 也没有 MCP 面
- 在 `MessagingAdapter` 上直接加订阅与 cursor 方法: 最强理由是只有一层抽象, 改动集中在 `types.py`. 否决原因是订阅, 整形, 幂等是跨平台共性逻辑, 放进适配器会每个平台各写一遍且行为不一致, 而且 `server/messaging/` 已有 5 个 py 文件, 再加会突破目录文件数约束
- 引入 Redis Streams 或 NATS 作为消息总线: 最强理由是背压, 消费者组与持久化都是现成的. 否决原因是多一个常驻进程与几十 MB 内存, 与内存最小化目标冲突, 单实例 SQLite 部署下自增 id 已足以充当有序日志
- 独立仓库独立进程的网关: 最强理由是故障隔离彻底, 可独立发布. 否决原因是同仓部署已经确定, 独立进程要重复用户体系, 加密密钥与 NapCat 引擎管理, 并额外多一个 Python 解释器的常驻内存
- 用 NoneBot2 或 Koishi 作为路由核心: 最强理由是已有大量平台适配器与插件生态. 否决原因是它们的核心抽象是机器人事件处理器, 没有可寻址的 source 与 sink, 也没有面向外部调用方的 cursor 与投递状态, Koishi 还会多一个 Node 进程
- GitHub 用 PAT 加定时轮询: 最强理由是配置简单且不需要公网回调. 否决原因是轮询违背 CPU 目标, PAT 权限粗且绑定个人账号, GitHub App 有细粒度权限与独立额度

## Consequences

- AI 获得跨平台一致的 MCP 工具集, 新增平台只多出新的 session 地址前缀, 不改工具定义
- 监听不再依赖轮询, 空闲 CPU 与内存有可测量上限, 这些数字成为实现阶段的验收项
- 出站必须经过 outbox 与整形器, 同一会话连发会被拉开到至少 3 秒一条, 单条最低延迟变大
- 新增 `router_routes`, `router_outbox`, `router_ingress_deliveries`, `router_api_keys` 四张表, `messaging_messages` 增加 6 列与基于 `dedup_key` 的唯一索引, 旧行 `dedup_key` 为空不受约束, 迁移不需要清理重复行
- 部署需要为 GitHub webhook 提供公网 HTTPS 回调地址
- 路由层已落地: `server/router/` 下有 provider 协议, 三个核心原语 cursor, envelope, errors, 以及 impl 下的 store, reader, outbox, outbox_admin, shaper
- QQ 与 GitHub 两个 provider 已接入同一份 `MessagingProvider` 协议, 平台差异只体现在 providers 目录里, 路由层不认识任何平台
- `outbox` 与 `outbox_admin` 拆开是行数约束驱动的, 但切在真实接缝上: 前者是发送流水线 (入队, 领取, 回结果), 后者是运维面 (查投递, 挂起实例, 重启恢复, 保留期清理)
- `models/messaging.py` 增加 6 列与两张部分唯一索引, 迁移幂等, 老库连跑两次不报错, 老行 `dedup_key` 为空不受唯一索引约束

## Testing

已落地的自动化覆盖在 `server/tests/test_router_core.py` (42 项), `test_router_qq.py` 与 `test_router_github.py` (合计 78 项)
- cursor 往返与非法输入拒绝, 增量读不重不漏且翻页数为 5, 前缀读与全平台读, 跨实例与越界 cursor 拒绝, 保留期删除后标记 gap
- 单会话读走 `idx_messaging_messages_instance_chat` 索引, 由 EXPLAIN QUERY PLAN 断言, 不允许出现 SCAN
- 入站去重同一 dedup_key 不写第二行, 编辑事件就地覆盖文本, raw 超 16 KB 落盘且行内清空
- 两类出站幂等键, 领取独占, 重试矩阵, 限流等待不消耗次数, give_up_at 到期判 failed, 重启把 send 行置 unknown 而 webhook 回 queued
- 令牌桶同会话 3 秒间隔, 账号分钟窗口与每日上限, 两个 profile 可配置, 相同文本 30 秒内扇出到不同会话被拒
- 迁移在旧库上连跑两次不报错, 新列与新表齐备
- 门禁是 `bash scripts/verify.sh` 全绿 (9 关, 570 项后端测试加 Playwright)
