# Agent Note: MCP 补全 (会话, GET 流, resources 与通知, outputSchema, API Key scope)

Status: implemented

Decision-ID: mcp-completion

## Code

- `server/src/hx_email/api/impl/mcp/session_table.py`
- `server/src/hx_email/api/impl/mcp_resources/watch.py`
- `server/src/hx_email/api/impl/gateway/auth.py`
- `server/src/hx_email/server/access/scopes.py`
- `server/src/hx_email/models/messaging.py`

## Problem

阶段 7 要把 `/mcp` 从 "无状态, 只有 POST" 补成完整的 MCP Streamable HTTP: `Mcp-Session-Id` 会话, `GET /mcp` 的服务端推送流与续传, resources (list 分页, templates, read, subscribe) 与 `notifications/resources/updated` / `list_changed`, 每个工具的 `outputSchema`, 以及 API Key 的 scope (MCP 与 REST 都校验). 约束是小内存, 不加缓存, 会话与订阅有上限并会过期, 已有 key 迁移后不能失去能力.

## Decision

- 会话 (`api/impl/mcp/session_table.py`): 进程内存表, 全局 256, 每凭据 8, 空闲 30 分钟过期, 无后台定时器; 会话绑定 bearer 令牌的 SHA-256, 别的凭据拿同一 id 得 404. 缺头 400, 未知或过期 404, `DELETE /mcp` 204. 协议版本协商 2025-06-18 与 2025-03-26, 不认识的 `MCP-Protocol-Version` 头 400.
- GET 流 (`api/impl/mcp/transport.py`): 一会话一条, 新流顶替旧流; 64 帧环形缓冲按会话内序号续传 `Last-Event-ID`; 未开过流不缓冲; 同 URI 通知合并; 15 秒注释心跳; 断开时 Starlette 取消生成器, `finally` 解除挂载. `/mcp` 路由挪到路由表最前, 否则根路径 `GET /{filename}` (Google 站点验证) 会先匹配.
- resources (`api/impl/mcp_resources/catalog.py`): capabilities, sources, instances/{id}, sessions/{session}/messages{?cursor,limit}, subscriptions/{id}, deliveries/{id}; 读时现查, 列表来自两条按用户索引的查询, 每页 50.
- 通知 (`api/impl/mcp_resources/watch.py`): 订阅即常驻 hub 等待者, 回调只入会话缓冲; 订阅与实例增删时 `announce_list_changed`. 每会话最多 32 个订阅.
- outputSchema (`api/impl/mcp/output_schemas.py`): 13 个工具都有, 只钉住依赖的键; 成功返回 `structuredContent` + 文本块, 错误只带文本块.
- scope (`server/access/`): 能力命名, `admin` 蕴含全部; 列 `router_api_keys.scopes` 以旧能力集为默认值加入; REST 各入口显式声明 scope (缺省 `router:read`), 不足 403 `insufficient_scope`; MCP `tools/list` 按 scope 过滤, 调用与 resources 方法不足时 JSON-RPC -32003. 前端订阅页新建密钥可勾选 scope, 已有密钥可改.

## Alternatives considered

- 什么都不做 / 复用现有方案, 保持无状态 POST, 监听继续靠 `events_wait` 与 `subscription_wait` 长轮询: 最强理由是零新状态, 零新内存. 否决: 规范客户端拿不到会话, 推送流与资源通知, 每个工具也没有 `outputSchema`; 一把 key 只能全有或全无, 无法发只读 key 给 Agent.
- 会话落库: 最强理由是重启不丢. 否决: GET 流与 hub 等待者重启必丢, 落库只留空壳; 规范要求 404 后重新初始化. 见 ADR 0011.
- 多条 GET 流同时收通知: 最强理由是多个标签页可各开一条. 否决: 规范要求一条消息只走一条流, 续传也会变成多序列.
- 每条通知无条件进缓冲: 最强理由是续传最完整. 否决: 客户端不开流时会话会白白攒消息; 合并后缓冲最多是订阅数加一条, 内存有界.
- 用官方 SDK: 否决, 理由同 ADR 0005.
- scope 按入口分 (`rest:send`, `mcp:send`): 否决, 同一能力两个开关容易配出不一致.
- 存量 key 迁移为只读: 最强理由是最小权限. 否决: 会把正在跑的脚本与 Agent 锁在外面, 违背 "迁移后能力不变" 的要求; 收紧交给用户在前端改.

## Consequences

- 多进程部署时会话不共享, 需要按 `Mcp-Session-Id` 粘性路由或外部共享存储 (ADR 0011).
- 重启后客户端要重新 initialize 与 subscribe; 缓冲外的通知不补, 以 cursor 读取为准.
- `deliveries/{id}` 不可订阅 (投递状态不经 hub); 实例在线状态变化不触发 `updated`, 只有落库消息触发.
- scope 每次请求现查, 改权限对已有会话立即生效.
- WebSocket 订阅流 scope 不足时以 4404 + reason `insufficient_scope` 关闭 (沿用原有的 RouterError 分支).
