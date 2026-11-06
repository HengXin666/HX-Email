# Agent Note: 路由网关门面落地, REST 与 MCP 共用一组 server/gateway 函数, 所有出站经单线程分发与整形

Status: implemented

Decision-ID: router-gateway-facade

## Code

- `server/src/hx_email/server/gateway/sending.py`
- `server/src/hx_email/server/gateway/impl/dispatch.py`
- `server/src/hx_email/api/impl/gateway/rest_routes.py`
- `server/src/hx_email/api/impl/messaging/action_routes.py`
- `server/src/hx_email/server/messaging/store.py`
- `server/src/hx_email/server/router/impl/outbox_admin.py`

## Problem

`.agents/notes/implemented/feature/2026-11-02-messaging-router-gateway.md` 定下的路由层只落了零件: provider, shaper, outbox, reader 都有单测, 但生产代码里没有任何地方构造它们. 用真实 app 跑一遍 (TestClient, 一个 QQ 实例加一个 GitHub 实例) 得到:

1. `GET /api/v1/router/sources` 与 `POST /mcp` 都是 404, 规格第 5, 6 节的统一接口不存在, AI 无从调用.
2. 前端发送直调 `OneBotAdapter.send_message`, 不过整形器也不过熔断, 这是封号风险最大的一条路径.
3. QQ `conversations` 与 `groups` 在 OneBot 不通时抛出未捕获的 `MessagingError`, 返回 500.
4. GitHub 实例没有适配器, `/api/v1/messaging/instances/{id}/...` 每个接口都是 400 `Messaging kind 'github' is not available yet`.
5. 事件端点同一 OneBot 事件投两次入库两行, `dedup_key` 为空, `chat_id` 为纯号.

## Decision

- 新增 `server/gateway/` 作为路由层唯一公开入口: `providers.py` 按实例解析 provider 并持有进程级 `SHAPER`, `catalog.py` 提供 sources / sessions / select, `listen.py` 负责入库去重, cursor 读取与长轮询, `sending.py` 负责 send / delivery / hold / resume, `api_keys.py` 管 `hxr_` 路由 Key. `server/router/` 目录已满 5 个文件, 所以门面放新目录, 依赖方向是 gateway -> router, 反向禁止.
- REST (`/api/v1/router/*`) 与 MCP (`POST /mcp`) 调同一组函数, 前端的会话, 消息与发送也改走这组函数, 三个入口共享幂等, 整形, 熔断.
- 出站一律先写 `router_outbox`, 再由 `impl/dispatch.py` 的单个守护线程按 熔断 -> 整形 -> 抖动 -> provider.send 的顺序投递. 调用方用 `wait_seconds` (0 到 5 秒) 选择同步等结果还是立即拿 `queued` 异步返回.
- 空闲零开销: 分发线程在队列空时无超时等待 `Event`, 有排队行时只睡到 `MIN(next_attempt_at)`; 监听用 `threading.Condition` 版本号, 入库时 notify, 无人等待时没有任何定时器.
- MCP 自实现无状态 JSON-RPC (initialize, ping, tools/list, tools/call), 不引官方 SDK.
- 风控熔断 `impl/breaker.py`: 5 分钟 3 次风控类失败停发 30 分钟, 当天第二次 6 小时, 第三次 `manual_hold`, 只能由前端会话调用 resume 解除.
- QQ 事件入库改走 `ingest_qq_event`: 完整会话地址, `(instance_id, dedup_key)` 唯一, 重投只落一行. GitHub 实例用只答状态的 `GitHubAppAdapter`, 让前端能打开实例; 插件目录登记 `github` 种类 (`adapter_factory=None`), 新建实例接口拒绝这类无工厂的种类, GitHub 只能经 App Manifest 流程接入.
- 老页面读消息仍传纯号, `store.list_messages` 同时匹配纯号与完整地址 (`%:<instance>:%:<peer>`).
- `outbox_admin.record_result`: `send` 行拿到 provider `failed` 直接终态, 不再按退避重试; 被风控或禁言的号反复重发正是封号路径, 风控信号交给熔断器处理.

## Alternatives considered

- 什么都不做, 继续让前端直调适配器: 最强理由是零改动, 现有前端照常能发. 否决: 这条路径没有任何限流, 一个脚本循环就能把小号送进风控, 而用户把 "不能被封号" 列为第一核心点.
- 用官方 `mcp` Python SDK 挂 streamable HTTP: 最强理由是协议细节由 SDK 维护, 将来加 resource 订阅省事. 否决: 我们只需要 4 个方法, SDK 会引入额外依赖树并为每个会话常驻任务组, 与 "内存尽量小" 冲突; 规格里 tool 的入参与返回不变, 以后换 SDK 只动 `mcp_server.py`.
- 每个实例一个分发线程或 asyncio 任务: 最强理由是账号之间互不阻塞. 否决: 单线程天然串行化同一账号的发送, 与整形器 "一个账号一个桶" 的假设一致, 而且线程数不随实例数增长; 抖动 sleep 只有几百毫秒到 3 秒, 多账号串行的代价可以接受.
- 在 `server/router/` 里直接加 facade.py: 最强理由是与规格第 1 节的文件表一致. 否决: 该目录已有 5 个 py 文件, `scripts/check_arch.py` 不允许第 6 个.
- 自动熔断状态落库: 最强理由是重启后不丢. 否决: 每实例几个浮点数, 重启后整形器的保守窗口仍在; 需要跨重启保持的手动暂停已经把排队行置为 `held` 落在 outbox 里.

## Consequences

- `SHAPER` 必须是进程单例, 任何新出站入口都要经 `sending.send_message`, 绕过它就等于绕过限流.
- 多进程部署 (多个 uvicorn worker) 会让每个进程各有一个桶与一个分发线程, 限流被放大; 部署保持单进程 (ADR 0002).
- 熔断的自动部分重启即丢, 手动部分靠 outbox 的 `held` 行保持, resume 后自动续发.
- 路由订阅表 (`route_subscribe`, webhook 推送) 未在本轮实现; 监听靠 `events_wait`, `GET /api/v1/router/wait` 与 SSE `GET /api/v1/router/stream`.
