# 0011 MCP 会话与 GET 流放在进程内存, 资源订阅复用 hub, API Key 按能力分 scope

## Status

Accepted (2026-11-09). 修订 ADR 0005 中 "MCP 无状态, 不开 SSE 通道" 的做法; 继续不引入官方 `mcp` SDK.

## Context

阶段 7 要补齐 MCP Streamable HTTP 的另一半: `Mcp-Session-Id` 会话, `GET /mcp` 的服务端推送流, resources 与 `notifications/resources/updated`, 工具的 `outputSchema`, 以及按权限划分的 API Key. 约束: 单进程部署 (ADR 0002), 小内存, 空闲时零 CPU, 不加缓存.

## Decision

- 会话表只在进程内存: `Mcp-Session-Id` 是 24 字节随机串, 绑定发起它的凭据 (bearer 令牌的 SHA-256). 全局 256, 每凭据 8 (挤掉最久未用的), 空闲 30 分钟过期; 清理顺带在创建与查找时做, 没有后台定时器. 重启后会话全部失效, 客户端按规范收到 404 再 `initialize`.
- GET 流: 每个会话一条, 新流顶替旧流, 所以一条通知只走一条流; 每会话 64 帧环形缓冲支持 `Last-Event-ID` 续传; 从未开过流的会话不缓冲; 同一资源的 `updated` 在送出前合并为一条. 流在 `asyncio.Event` 上睡, 不占线程; 跨线程唤醒用 `call_soon_threadsafe`, 所以发布线程与不同事件循环都安全.
- 资源订阅 = 一个常驻 hub 等待者 (阶段 2 的 `BUS`), 匹配器从资源推出; 回调只往会话缓冲放一条通知, 不碰数据库. 通知只是提示, 数据以 `resources/read` 或 cursor 读取为准, 丢通知不丢数据.
- scope 按能力命名而不是按入口 (`router:read`, `router:send`, `router:actions`, `subscriptions`, `resources:subscribe`, `mcp`, `admin`), REST 与 MCP 共用; `admin` 蕴含全部. 存量 key 迁移时取除 `admin` 外的全部 scope, 等于引入 scope 前的能力. key 管理与 hold/resume 仍只认控制台会话, 与 scope 无关.

## Alternatives considered

- 会话持久化到 SQLite: 重启不丢会话. 否决: 会话里真正有价值的是 GET 流与 hub 等待者, 二者重启后必然消失; 存一个空壳只会让客户端以为订阅还在. 规范本来就要求客户端在 404 后重新初始化.
- 允许同一会话多条 GET 流并各自收全部通知: 否决, 规范要求每条消息只走一条流; 轮流分发又让续传语义复杂.
- 引入官方 SDK 的 Streamable HTTP 实现: 否决理由同 ADR 0005 (依赖树, 每会话任务组, 与现有 hub 与鉴权的接缝), 自实现部分不到 600 行.
- scope 按入口划分 (`rest:*`, `mcp:*`): 否决, 同一能力两个开关容易配出 "REST 能发, MCP 不能发" 的不一致; 只保留 `mcp` 一个入口开关用来做纯 REST 的 key.

## Consequences

- 多进程或多副本部署时, 会话只存在于创建它的进程: 需要按 `Mcp-Session-Id` 做粘性路由, 或把会话表与通知缓冲搬到共享存储 (例如 Redis pub/sub). 当前部署是单进程, 不做.
- 重启或会话过期后, 客户端要重新 `initialize` 并重新 `resources/subscribe`; 缓冲以外的通知无法补发, 客户端用 cursor 读取补齐.
- 会话按凭据绑定: 同一把 key 换了明文 (重新签发) 就是新凭据, 旧会话 404.
- 已用官方 python SDK 2.3.0 与 Inspector CLI 2.14.0 实测互通 (docs/messaging-router.md 5.15 末尾); SDK 发起 `2025-11-25` 时降级到 `2025-06-18`. 若以后要支持 `2026-07-28` (无握手的 `discover` 与 `listen`), 需要另开 ADR.
