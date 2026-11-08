# Agent Note: 路由 hub 按命中唤醒, 持久订阅落到 router_routes, 长轮询与 SSE 改协程不占线程池

Status: implemented

Decision-ID: router-hub-subscriptions

## Code

- `server/src/hx_email/server/hub/consume.py`
- `server/src/hx_email/api/impl/subscriptions/subscription_routes.py`

## Problem

契约 v2 之后网关能读能发, 但监听侧有三个硬伤:

1. 每次落库都 `notify_all` 进程里唯一的条件变量, 所有用户的所有等待者一起醒来各跑一遍 SQL, 消费者一多就是惊群.
2. `/router/wait`, MCP `events_wait` 与 `/router/stream` 在等待期间一直占着线程池的一个线程, 几十个空闲连接就能把 API 的同步路由饿死.
3. 没有持久订阅: `router_routes` 表建了但没有任何读写代码, 消费者重启只能自己记 cursor, 服务端也不知道谁在听什么, 前端更无从展示.

## Decision

- 新目录 `server/hub/`: `bus.py` 维护等待者注册表, 每个等待者带一个由 source 与可读实例生成的匹配器 (精确会话, v2 选择器的 LIKE 模式按同样转义规则转成正则, 会话类型, 方向); 每次落库 `publish(Hit)` 只唤醒命中的等待者. 匹配器宁可多不可漏, 误唤醒者按 cursor 重读一次再睡.
- `consume.py`: 所有等待都是协程, 先注册等待者再读库 (借一次工作线程), 然后睡在 `asyncio.Event` 上, 跨线程用 `call_soon_threadsafe` 唤醒. REST `/wait`, `/stream`, 订阅的 `/events`, `/stream`, MCP `events_wait` 与 `subscription_wait` 全走这里; MCP 端点识别 hub 工具后直接 await, 不再进线程池.
- `subscriptions.py`: `router_routes` 的增删改查与 ack; 过滤条件作用在 Event v2 视图上; ack 只前进; 每账号上限 50; 迁移补 `name`, `updated_at` 两列与索引.
- 新 API 目录 `api/impl/subscriptions/` 放订阅 REST 路由与 MCP 订阅工具 (`api/impl/gateway/` 已满 5 个文件).
- 前端新增 "消息订阅" 页: hub 状态, 新建 (按账号给出常用来源), 列表与积压, 暂停与删除, 通过 fetch 读 SSE 的实时事件与确认, 路由密钥管理, 带入订阅 id 与密钥的 cURL, Python, SSE, MCP 配置示例.

## Alternatives considered

- 什么都不做, 保留单条件变量加线程池等待: 最强理由是实现最简单, 空闲时同样零 CPU. 否决: 唤醒量与等待者总数成正比, 线程池上限直接成为并发监听上限, 而且持久订阅仍然没有.
- 复用现有条件变量, 只把等待挪到 `anyio.to_thread` 之外 (协程里轮询版本号): 最强理由是改动小. 否决: 要么定时轮询 (违背 ADR 0005 的 A2 空闲零定时器), 要么仍然需要一个跨线程唤醒协程的机制, 那就是本方案的 bus.
- 用外部消息中间件 (Redis pub/sub, NATS) 做 hub: 最强理由是天然支持多进程. 否决: 网关本来就因单派发线程只能单进程运行, 引入中间件增加部署依赖却换不来收益; publish 接口保持 `Hit` 列表, 以后换实现不影响调用方.
- 订阅 id 沿用设计稿的 `r_12` 字符串: 最强理由是与文档一致. 否决: 表主键就是整数, 加前缀只增加解析与校验; 文档 5.13 已更正.

## Consequences

- 空闲监听只占一个协程与一个集合元素, 一条消息只唤醒与它相关的消费者.
- hub 在进程内; 多进程部署需要把 publish 换成共享通道.
- 长轮询不推进 ack, 消费者处理完要显式确认, 否则下次从旧位置重放 (至少一次); SSE 可选推出即确认.
- webhook, WebSocket (阶段 3) 与 MCP resource 通知 (阶段 7) 复用同一张表与同一个 publish 调用.
