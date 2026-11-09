# Agent Note: 推送通道, webhook 签名投递与退避, WebSocket 订阅流, 先拆 envelope 与 reader

Status: implemented

Decision-ID: router-push-transports

## Code

- `server/src/hx_email/server/push/webhook_deliver.py`
- `server/src/hx_email/server/hub/subscriptions.py`
- `server/src/hx_email/api/impl/subscriptions/ws_routes.py`

## Problem

阶段 2 之后订阅能持久化, 但只能拉: 长轮询或 SSE. 作为 Agent harness 的消息基建还缺两条:

1. 服务端主动推送. 很多消费者 (无常驻进程的函数, 别人的服务) 只能被 HTTP 回调, `router_outbox` 的 `kind='webhook'` 行, 每路由串行领取与重启回退早已写好, 但派发线程遇到 webhook 行直接标 `failed`, 没有任何代码产生这类行.
2. 双向长连接. SSE 只能下行, 确认要另发 POST; 浏览器与很多 Agent 框架更习惯 WebSocket, 并希望在同一条连接上 ack.

另外 `server/router/envelope.py` 与 `server/router/impl/reader.py` 都正好 300 行, 所在目录也都已有 5 个文件, 任何改动都会越过 AGENTS.md 的上限.

## Decision

- 先拆分, 不改行为: `envelope.py` 变成包 `envelope/` (`session.py` 地址, `model.py` envelope 与校验, `raw.py` raw 落盘与时间), `impl/reader.py` 变成包 `impl/reader/` (`source.py` 范围与查询, `rows.py` 行转 envelope, `page.py` 分页读取); 两个包的 `__init__.py` 重新导出全部旧名字, 调用方的导入路径不变, 只有 `listen.py` 改用公开名 `row_to_envelope`.
- 订阅行增加推送字段: `delivery` 取 `pull` 或 `webhook`; webhook 的 URL 与密钥加密存进已有的 `target_encrypted`; 新列 `push_cursor` 记录已排批到哪里, 与 `ack_cursor` 分开. 密钥只在创建, 切换为 webhook 或轮换时返回一次. 为了不越过 300 行, 行模型拆到 `hub/route_model.py`.
- 新目录 `server/push/`: `webhook_target.py` 管 URL 校验, 加密, 签名; `webhook_feed.py` 是一个守护线程, 为每条活跃 webhook 订阅按其范围注册一个 hub 等待者, 命中时从 `push_cursor` 读取, 过滤后每 50 条排成一个 `kind='webhook'` 批次 (幂等键为首尾消息 id), 再唤醒派发线程; `webhook_deliver.py` 负责 POST.
- 投递: 派发线程领到 webhook 行后交给 4 个线程的小池, 慢接收端不拖住平台出站; 同一订阅同时只有一批在途, 接收端按序收到. 请求体是排批时固化的 JSON, 头带 `X-HX-Router-Signature: sha256=<hex>` (HMAC-SHA256 整个请求体), `X-HX-Router-Delivery`, `X-HX-Router-Subscription`. 2xx 置 `sent` 并把 ack 推到该批 `next_cursor`; 其它情况 10 秒起翻倍到 1 小时, 加 20% 抖动, 到 `give_up_at` (24 小时) 置 `dead`; 订阅暂停时到点的批次置 `held`, 恢复时重新排队. `seconds_until_next` 跳过有在途批次的订阅, 避免派发线程空转.
- 管理接口: `/subscriptions/{id}/deliveries` (投递记录), `/deliveries/{delivery_id}/redeliver` (重投 dead 或 failed), `/webhook/ping` (同步发一次签名的 ping), `/webhook/rotate` (轮换密钥). 删除订阅时一并删除它的 webhook 行.
- WebSocket: `/subscriptions/{id}/ws`, 与 SSE 共用 `consume.iterate_source`; 服务端帧 `ready`, `messages`, `heartbeat`, `acked`, `pong`, `error`, 客户端帧 `ack` 与 `ping`; 关闭码 4401, 4404, 4409. 浏览器不能给 WebSocket 设 Authorization, 令牌可放在子协议 `bearer.<token>`, 服务端回应 `hx-router`. 一条连接上的发送用锁串行. 下行 (pump) 与上行 (listen) 跑在一个 anyio 任务组里, 先结束的一方取消另一方; 不用裸 `asyncio.wait`/`gather`, 因为收尾靠 anyio 取消作用域, 混用时客户端关闭与作用域取消赛跑, CancelledError 会漏出作用域 (CPU 负载高时测试偶发).
- 前端订阅页: 新建时可选投递方式与 Webhook 地址, 一次性展示密钥; Webhook 面板 (改地址, 测试推送, 轮换密钥, 投递记录与重投); 实时事件可选 WebSocket 或 SSE, WebSocket 下 "确认到最新" 走同一条连接; 接入示例增加 WebSocket 客户端与带签名校验的 webhook 接收端, Python 示例在没有订阅时先创建订阅. Vite 代理打开 `ws`.

## Alternatives considered

- 什么都不做, 继续只提供长轮询与 SSE: 最强理由是消费者自己起一个循环就能拉, 服务端最简单. 否决: 没有常驻进程的消费者无法接入, 而 webhook 的队列语义早在 outbox 里设计好了, 只差生产者与投递者.
- 复用现有 `record_result` 的重试规则投 webhook: 最强理由是一套代码. 否决: 那套规则是平台出站的 4 次尝试与 15 分钟上限, 规格 7.4 要求 webhook 以 24 小时为界; 而且 `failed` 对平台出站是终态, 对 webhook 应是 `dead` 并可手动重投. 两类行只共用领取与幂等, 结果记录分开.
- 在派发线程里同步 POST: 最强理由是天然串行, 不需要线程池. 否决: 一个 10 秒超时的接收端会让所有账号的平台发送排队 10 秒, 而平台出站的整形与熔断假设派发线程不被外部 HTTP 卡住.
- webhook 不排批, 消息到达即直接 POST: 最强理由是延迟最低, 少一张表的写入. 否决: 进程重启或接收端停机时会丢消息; 先入 outbox 才有幂等键, 重启回退与按序补投.
- WebSocket 令牌放 query 参数: 最强理由是所有客户端都支持. 否决: URL 会进访问日志与浏览器历史; 子协议与 Authorization 头都不会.
- envelope 与 reader 只把几个函数挪进现有目录的其它文件: 最强理由是不新增包. 否决: 两个目录都已满 5 个文件, 挪函数只会让别的文件逼近 300 行; 拆成包并在 `__init__` 重新导出, 旧导入路径一个不改.

## Consequences

- 投递语义仍是至少一次: 接收端按 `X-HX-Router-Delivery` 或 envelope `id` 去重.
- 订阅范围内整页消息都被过滤且没有在途批次时, ack 随 `push_cursor` 前移, 积压不虚高; 有在途批次时被过滤的尾部要等下一批成功才计入.
- feeder 与派发线程都在进程内, 与 hub 一样只支持单进程部署.
- webhook URL 只校验 http(s) 与不含凭据, 不拦截内网地址; 多租户部署需要再加 SSRF 防护.
- 停机 1 小时后按序补投依赖退避上限 1 小时, 只有单元测试覆盖了退避与 dead 的边界, 没有真实时长的演练.
