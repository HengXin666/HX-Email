# Agent Note: 消息能力升级为路由网关, 适配器只做平台连接, 订阅与分发收敛到独立路由层

Status: proposed

Decision-ID: messaging-router-gateway

## Code

- `server/src/hx_email/server/messaging/types.py`
- `server/src/hx_email/api/impl/messaging/event_routes.py`
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

在同仓新增 `server/router/` 路由层, 统一使用 source, sink, route, envelope, cursor 五个概念
- 适配器是平台连接, 路由层是订阅与分发, 适配器通过一个更窄的 `MessagingProvider` 协议成为路由层的 provider
- 依赖方向为 路由层 -> provider -> adapter, `server/messaging/` 不 import 路由层, 现有适配器签名不改
- 对外以 MCP server 为主 (`/mcp` streamable HTTP 与 `hx-email mcp` stdio), REST 兼容面在 `/api/v1/router`, 与 MCP tool 一一对应
- 现有前端继续使用 `/api/v1/messaging`, 内部改为共享同一张消息表, 同一套 cursor 与同一个 outbox

同步与异步
- 同步路径是 send, list, fetch, 发送默认等待至多 5 秒拿到平台消息 ID, 超时返回 queued
- 异步路径是订阅加推送, MCP 用 resource 通知与长轮询 tool, 外部用 SSE 与签名 webhook
- 背压原则是通知可以丢, 数据不会丢, 每订阅者信号队列上限 256, 溢出标记 gap 由消费者按 cursor 补读

稳定性
- QQ 不做任何协议自研, 只用 NapCat 的 OneBot 11, Lagrange.OneBot 为同接口备用
- 每个 QQ 账号独立实例与独立容器, session 地址绑定唯一实例, 不做跨号切换发送
- 出站经过令牌桶整形, QQ 默认同会话 3 秒间隔, 账号每分钟 20 条, 突发 3 条, 每日 1000 条, 附加随机抖动
- 出站以 `(instance_id, kind, idempotency_key)` 幂等, 入站以 `(instance_id, platform_message_id)` 去重
- 可重试错误指数退避, 风控信号触发该账号出站熔断 30 分钟

资源占用
- QQ 与 GitHub 都是平台推送, 路由层没有周期性拉取循环, 唯一常驻定时器是 60 秒一次的 housekeeping
- 读取全部按 cursor 增量走索引, 大于 16 KB 的 raw 落盘, 信号队列只存 cursor 不存消息体
- 验收项写成可测量数字, 空闲 CPU 不超过单核 0.5%, 启用路由层后 RSS 增量不超过 40 MB, NapCat 容器限制 512 MB 内存

GitHub
- 使用 GitHub App, webhook 接收事件并以 `X-Hub-Signature-256` 校验, installation token 发评论与建 issue
- 权限最小集为 Metadata 只读, Issues 读写, Pull requests 读写

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
- 新增 `router_routes` 与 `router_outbox` 两张表, `messaging_messages` 增加去重唯一索引, 迁移前要先清理已有重复行
- 部署需要为 GitHub webhook 提供公网 HTTPS 回调地址
- 本 note 在 proposed 阶段, `## Code` 中的三个文件需要在实现提交里补上指向本 note 的声明锚点, 落地时连同锚点一起移到 implemented

## Testing

本 note 处于 proposed, 下面是实现提交必须带上的验证
- cursor 增量读, 越界 cursor 与跨实例 cursor 拒绝, 由 `server/tests/test_router_cursor.py` 覆盖
- 出站幂等, 令牌桶间隔, 退避上限, 熔断与恢复, 由 `server/tests/test_router_outbox.py` 覆盖
- OneBot 事件重投去重与 GitHub 签名校验, 由 `server/tests/test_router_ingress.py` 覆盖
- 全部 MCP tool 的入参 schema 拒绝多余字段, 由 `server/tests/test_router_mcp.py` 覆盖
- 空闲 CPU, 常驻内存与订阅者落后的数字验收项 A1 到 A6 在部署机上手工执行, 结果写回落地后的 implemented note
- 门禁是 `bash scripts/verify.sh` 与 `npm run verify-notes`
