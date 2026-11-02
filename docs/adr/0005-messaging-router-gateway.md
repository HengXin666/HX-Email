# 0005 消息路由网关 (Messaging Router Gateway)

## Status

Proposed

## Context

`docs/messaging-plugins.md` 已经把 HX-Email 的消息能力做成了插件模式, 现有事实如下
- 平台连接由 `server/src/hx_email/server/messaging/types.py` 中的 `MessagingAdapter` 抽象承担, QQ 侧唯一可用实现是 `onebot.py` 里的 `OneBotAdapter`
- QQ 协议端不自研, 由 `engine.py` 的 `QQEngineManager` 按实例拉起 NapCat Docker 容器, 通过 OneBot 11 HTTP 接口收发
- 入站消息经 `POST /api/v1/messaging/events/{kind}` 回调, 由 `impl/events.py` 的 `ingest_event` 转成 `MessagingMessage` 后写入 `messaging_messages`
- 对外只有面向前端页面的 REST, 前缀为 `/api/v1/messaging`, 路由表见插件文档第 4 节

这一轮的产品定位发生了变化, 下面是对用户定位的忠实转述
- 这个服务要充当一个消息路由, 提供大量的消息监听入口与消息输出出口
- 它是基建服务, 调用方可以选定 QQ 的某个账号, 再选定该账号下的某个会话, 然后监听这个会话的内容, 也可以向它发送内容
- 平台支持无限扩展, 除 QQ 之外还要覆盖微信, Telegram, 以及 X 这类论坛型平台
- 各平台的消息获取 API 与消息发送 API 要聚合成一个通用接口, 以 MCP 这类形式提供给 AI 调用和监听
- 当前优先支持 QQ 的监听与发送, 以及 GitHub 的监听与发送, GitHub 侧使用 GitHub App 方案
- QQ 侧不实现任何通信协议, 只基于市面上现成的库
- 两个核心关注点是稳定性与资源占用, 稳定性指不能因为接入而导致账号被封, 资源占用指内存尽量小且 CPU 不能长期保持较高消耗
- 同步与异步都要支持, 消息的监听与推送也都要支持

已经确定且不再讨论的两条
- 新服务在 HX-Email 仓库内长出独立模块, 复用现有 `server/messaging/` 与 NapCat 引擎, 与邮箱业务解耦但同仓部署
- 对外接口以 MCP server 为主, 同时保留 REST 兼容面供脚本与 webhook 使用

现有代码与新定位之间的缺口
- `MessagingAdapter` 只有 "连接一个平台账号" 的语义, 没有 "谁在监听哪个会话" 的订阅概念, 也没有出口投递状态
- `messaging_messages` 没有去重约束, NapCat 重投同一事件会写出重复行
- 读消息只有 `ORDER BY id DESC LIMIT n` 的最新 n 条, 没有增量游标, 调用方无法可靠地 "只读新的"
- 发送是同步直发, 没有速率整形与幂等键, 对 QQ 个人号这类高风控平台是直接的封号风险
- `registry.py` 中 QQ 的描述与风险提示仍写着 lagrange-python, 而真实运行路径是 NapCat 容器加 OneBot 11, 这一处描述需要在实现阶段对齐

## Decision

### 1. 定位与统一动词

新模块叫消息路由网关, 是一个 "消息收发出入口" 基建服务, 不是聊天客户端
- 它不渲染会话界面, 不维护已读状态, 不做消息编辑体验, 这些仍属于前端页面
- 它只回答三件事, 哪些消息进来了, 谁要这些消息, 要发出去的消息是否送达

全部接口只使用下面五个概念
- source (监听源) 是一个可以产生入站消息的地址, 形如 `qq:<instance_id>:group:<group_id>` 或 `github:<instance_id>:repo:<owner>/<repo>`
- sink (输出口) 是一个可以接收出站消息的地址, 与 source 共用同一套地址语法, 同一个会话既是 source 也是 sink
- route (订阅规则) 把一组 source 绑定到一个消费者, 附带过滤条件与投递方式, 投递方式有 MCP 推送, SSE 与 webhook 三种
- envelope (统一消息信封) 是平台无关的消息结构, 公共字段加上 provider 私有的 `raw`
- cursor (增量游标) 是不透明字符串, 编码了 `messaging_messages.id` 的单调位置, 调用方凭它只读新增

与现有 `MessagingAdapter` 的关系
- 适配器是 "平台连接", 负责登录, 连接状态, 单条收发, 会话与群列表
- 路由层是 "订阅与分发", 负责 source 寻址, route 匹配, cursor 读取, 出站排队与整形, 投递状态
- 路由层通过一个更窄的 provider 契约使用平台能力, 现有 `MessagingAdapter` 由一个薄包装成为 QQ provider, 适配器本身不改签名
- 依赖方向固定为 路由层 -> provider -> adapter, 适配器永远不知道路由层的存在

### 2. 三类消费者共享一个模型

- MCP 客户端 (AI) 直接调用 tool 做同步收发, 通过 `resources/subscribe` 与长轮询 tool 获得异步推送
- REST 调用方 (脚本与 webhook) 使用 `/api/v1/router` 下与 MCP tool 一一对应的路由, 外部 webhook 作为 route 的一种投递方式
- 现有 HX-Email 前端页面继续使用 `/api/v1/messaging`, 其消息列表在实现阶段改为读取同一张表与同一套 cursor

三者读同一份 route 表, 同一份 envelope 序列化, 同一份 outbox, 差异只在传输层
- MCP 走 streamable HTTP, 挂在同一个 FastAPI 进程的 `/mcp`, 另提供 `hx-email mcp` stdio 入口给本机客户端
- REST 走普通 HTTP 与 SSE
- 前端走现有 REST

### 3. 同步与异步两条路

同步路径是请求响应式
- `send` 写入 outbox 并在整形器允许时立即投递, 默认等待至多 5 秒拿到平台消息 ID, 超时则返回 `queued` 与 `delivery_id`
- `list` 与 `fetch` 按 cursor 从数据库增量读取, 不触发平台侧拉取, 历史回补是显式的单独动作

异步路径是订阅加推送
- 入站消息落库提交之后, 路由层在进程内对匹配的 route 发出 "有新数据" 信号
- MCP 客户端收到 `notifications/resources/updated` 或长轮询 tool 返回, 然后凭 cursor 拉取
- SSE 连接收到事件帧, 帧内携带 envelope 与新 cursor
- webhook route 由 outbox 投递到外部 URL, 带 HMAC 签名

背压与丢弃策略的核心原则是 "通知可以丢, 数据不会丢"
- 每个在线订阅者有一个容量为 256 的进程内信号队列, 满了丢弃最旧的信号并在下一帧标记 `gap=true`, 消费者看到 gap 就按 cursor 补读
- 数据本身只在 SQLite 中, 任何订阅者落后都不会让服务端内存增长
- SSE 单帧最多携带 50 条 envelope, 超出部分只给 cursor 让消费者自己拉
- webhook 投递每个目标串行, 失败按指数退避重试 8 次, 累计超过 24 小时标记为 `dead`, 不再重试也不阻塞同目标的后续投递之外的其它目标
- 单个 route 的 webhook 积压超过 5000 条时暂停该 route 并在 `routes_list` 中报告 `paused_backlog`, 防止外部故障拖垮磁盘

### 4. 可扩展性与 provider 最小契约

新增一个平台只需实现一个 provider 并在注册表登记, 路由层零改动
- provider 只声明它能产生哪些 source, 能接收哪些 sink, 以及如何把平台事件翻译成 envelope
- 速率整形, 幂等, 重试, 订阅, cursor 都由路由层统一提供, provider 不得自行实现

```python
from dataclasses import dataclass
from typing import Literal, Protocol

DeliveryMode = Literal["push", "pull"]


@dataclass(frozen=True)
class ProviderLimits:
    per_session_interval_seconds: float
    per_account_per_minute: int
    burst: int
    daily_cap: int


@dataclass(frozen=True)
class SessionRef:
    address: str
    platform: str
    instance_id: int
    session_type: str
    session_id: str
    title: str


@dataclass(frozen=True)
class OutboundPayload:
    text: str
    reply_to: str
    idempotency_key: str


@dataclass(frozen=True)
class SendResult:
    platform_message_id: str
    retryable: bool
    risk_signal: bool
    error: str


class MessagingProvider(Protocol):
    platform: str
    delivery_mode: DeliveryMode
    limits: ProviderLimits

    def list_sessions(self, instance_id: int) -> list[SessionRef]: ...

    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult: ...

    def parse_event(
        self, instance_id: int, headers: dict[str, str], body: bytes
    ) -> list[dict[str, object]]: ...

    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool: ...
```

- `parse_event` 返回 envelope 字典列表, 允许一个平台事件拆成多条消息, 也允许返回空列表表示非消息事件
- `delivery_mode="push"` 表示平台主动回调 (QQ 的 OneBot HTTP 上报, GitHub webhook), `pull` 只留给没有回调能力的平台, 由路由层统一调度长连接或长轮询, 不允许 provider 自己起轮询线程
- QQ provider 的实现是对现有 `OneBotAdapter.send_message` 与 `list_conversations` 的包装, 加上对 `ingest_event` 的复用
- 未来的 Telegram 用 webhook 模式, Discord 用官方 gateway 长连接, X 这类平台走官方 API, 都只是新增一个 provider

### 5. 稳定性与不封号

QQ 侧明确不做任何协议自研, 只用 NapCat 的 OneBot 11 接口, Lagrange.OneBot 作为同接口的备用实现
- 独立号池: 每个 QQ 账号对应一个独立 `messaging_instances` 行与一个独立 NapCat 容器, 账号之间不共享登录态与进程, 一个号被风控不影响其它号
- 会话粘性: 一个 session 地址天然绑定唯一的 instance, 路由层不做跨账号的发送切换, 绝不出现 "这个号发不出去就换个号发" 的行为, 因为跨号轮换本身就是风控特征
- 发送速率整形: 每个 instance 一个令牌桶, QQ 默认同一会话最小间隔 3 秒, 账号级每分钟 20 条, 突发 3 条, 每日 1000 条, 每次发送附加 0.5 到 1.5 秒随机抖动
- 冷启动保护: QQ provider 只允许向 `list_sessions` 已返回的好友与群发送, 不向陌生号首发私聊
- 幂等与去重: 出站以 `(instance_id, idempotency_key)` 为唯一键, 同键重复调用返回同一个 `delivery_id`, 入站以 `(instance_id, platform_message_id)` 为唯一键, 重投事件被静默吸收
- 失败退避: 可重试错误按 2 秒起步翻倍, 上限 15 分钟, 最多 5 次, 不可重试错误直接终态
- 风控熔断: provider 返回 `risk_signal=true` (例如 OneBot 返回频率限制或账号异常类错误) 时, 该 instance 的全部出站暂停 30 分钟, 连续两次熔断则暂停到人工恢复, 状态通过 `sources_list` 可见

### 6. 内存与 CPU 空闲占用

架构手段
- 事件驱动: QQ 与 GitHub 都是平台推送, 路由层没有任何周期性拉取消息的循环
- 唯一的常驻定时器是每 60 秒一次的 housekeeping, 负责 outbox 到期重试与过期订阅清理, 其余时间进程阻塞在 I/O 上
- 连接复用: 每个 instance 复用一个 `requests.Session` 连接池, GitHub 侧 installation token 在内存中缓存到过期前 5 分钟
- 增量读: 所有读取按 cursor 加 `LIMIT` 走 `(instance_id, chat_id, id)` 索引, 不做全表扫描
- 大 payload 不驻留: envelope 的 `raw` 超过 16 KB 时落为数据目录下的文件, 表内只存引用, 读取时默认不带 `raw`
- 订阅信号队列只存 cursor 与 route 标识, 不存消息体

量化目标值, 以下全部写成验收项
- A1 空闲 CPU: 路由网关所在的 HX-Email 后端进程, 在 2 个 QQ 实例在线, 1 个 GitHub App 安装, 3 个活跃 SSE 订阅且无消息流量时, 连续 10 分钟平均 CPU 不超过单核的 0.5%, 用 `pidstat -u -p <pid> 60 10` 测量
- A2 唤醒次数: 同一空闲条件下, 进程每分钟由定时器引起的唤醒不超过 2 次, 用 `strace -c -f -e trace=epoll_wait,select,poll` 统计 60 秒
- A3 常驻内存增量: 启用路由网关与未启用相比, 后端进程 RSS 增量不超过 40 MB, 用 `ps -o rss= -p <pid>` 在启动 5 分钟后测量
- A4 负载后回落: 以 20 条每秒的入站速率持续 5 分钟后停止, 60 秒内 RSS 回落到峰值的 110% 以内, 且不高于 A3 基线加 60 MB
- A5 NapCat 容器: 每个 QQ 引擎容器以 `docker run --memory=512m --cpus=0.5` 启动, 空闲 10 分钟平均 CPU 不超过 2%, 用 `docker stats --no-stream` 采样 10 次
- A6 订阅者落后: 一个 SSE 订阅者停止读取 10 分钟, 期间入站 10000 条, 后端 RSS 增量不超过 5 MB

### 7. GitHub 侧

- 使用 GitHub App 而不是 PAT 轮询, 每个 App 安装对应一个 `kind="github"` 的 instance
- 入站全部依赖 webhook, 回调地址为 `POST /api/v1/router/ingress/github/{instance_id}`, 用 `X-Hub-Signature-256` 做 HMAC 校验, 用 `X-GitHub-Delivery` 作为入站去重键
- 出站用 App JWT 换取 installation access token, 再调用 REST API 发评论或建 issue, token 有效期 1 小时, 缓存复用
- 权限最小集: Metadata 只读, Issues 读写, Pull requests 读写, 其余权限一律不申请
- 订阅事件最小集: `issues`, `issue_comment`, `pull_request`, `pull_request_review_comment`
- session 粒度为仓库或单个 issue 与 PR, 地址形如 `github:<instance_id>:issue:<owner>/<repo>#<number>`
- GitHub 的速率整形同样经过路由层令牌桶, 默认账号级每分钟 30 次写操作, 与 GitHub secondary rate limit 留出余量

### 8. 密钥

- GitHub App private key, webhook secret, QQ 事件 token 都放进 `messaging_instances.config_encrypted`, 统一经 `security.encrypt_secret` 加密, API 返回时脱敏为 `***`
- MCP 与 REST 兼容面的调用凭据复用现有用户体系, 由用户在设置中生成路由 API Key, 服务端只存哈希

## Alternatives considered

- 什么都不做 / 复用现有 `/api/v1/messaging`: 最强理由是它已经能收发 QQ 消息, 有前端, 有测试, 零新增代码, 让 AI 通过 REST 调用也能工作. 否决原因是它缺少四个基建必需品, 没有增量 cursor 导致调用方只能反复拉最新 n 条并自己去重, 没有订阅导致监听只能轮询而违背 CPU 目标, 没有出站整形与幂等直接放大封号风险, 没有 MCP 面导致 AI 侧要为每个平台手写工具描述
- 直接在 `MessagingAdapter` 上加订阅与 cursor 方法: 最强理由是只有一层抽象, 概念最少, 改动集中在 `types.py`. 否决原因是订阅, 整形, 幂等是跨平台的共性逻辑, 放进适配器会让每个平台各写一遍且行为不一致, 而且 `server/messaging/` 已有 5 个 py 文件, 再加会突破目录 2 到 5 个文件的约束
- 引入外部消息总线 (Redis Streams, NATS): 最强理由是背压, 多消费者组, 持久化都是现成的, 将来多实例部署更容易. 否决原因是它新增一个常驻进程与几十 MB 内存, 与内存最小化目标正面冲突, 而当前单实例 SQLite 部署形态 (见 ADR 0002) 下 SQLite 自增 id 已经足够充当有序日志
- 独立仓库独立进程的网关服务: 最强理由是故障隔离彻底, 可以单独扩缩容与发布. 否决原因是用户已经确定同仓部署, 且独立进程会重复一份用户体系, 加密密钥与 NapCat 引擎管理, 空闲内存至少多一个 Python 解释器的开销
- 使用现成多平台机器人框架 (NoneBot2, Koishi) 作为路由核心: 最强理由是它们已经有 OneBot, Telegram, Discord 等大量适配器与插件生态. 否决原因是它们是 "机器人应用框架", 核心抽象是事件处理器而不是可寻址的 source 与 sink, 没有面向外部调用方的 cursor 与投递状态, 引入后要在它外面再包一层路由, 且 Koishi 是 Node 运行时会多一个进程
- GitHub 侧用 PAT 加定时轮询: 最强理由是配置简单, 不需要公网回调地址. 否决原因是轮询与 CPU 目标冲突, PAT 权限粒度粗且绑定个人账号, 而 GitHub App 提供细粒度权限与独立的速率额度
- QQ 侧自研或使用更轻的协议库以节省内存: 最强理由是 NapCat 容器常驻数百 MB, 是整套部署里最大的内存项. 否决原因是协议自研或非主流协议库的封号风险与维护成本远高于内存收益, 用户明确要求不做协议实现, 内存问题通过容器内存上限与按需启动实例来约束

## Consequences

- AI 获得一套跨平台一致的 MCP 工具, 新增平台不改工具定义, 只多出新的 source 地址前缀
- 监听不再需要轮询, 空闲 CPU 与内存有可测量的上限, 验收项 A1 到 A6 进入实现阶段的测试清单
- 出站必须经过 outbox 与整形器, 单条发送的最低延迟会增加, 同一会话连发会被拉开到至少 3 秒一条
- 数据库新增 `router_routes` 与 `router_outbox` 两张表, `messaging_messages` 新增去重唯一索引, 迁移需要先清理已有重复行
- 现有前端的消息列表需要切换到 cursor 读取, 旧的 `GET /instances/{id}/messages` 保持兼容一个阶段
- 部署需要为 GitHub webhook 提供可公网访问的 HTTPS 回调地址
- 实现规格见 `docs/messaging-router.md`, 决策记录见 `.agents/notes/proposed/feature/2026-11-02-messaging-router-gateway.md`
