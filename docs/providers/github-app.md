# GitHub Provider 接入方案 (GitHub App)

本文给出 HX-Email 消息插件体系中 GitHub 侧消息监听与发送的接入方案
本文只是设计文档, 不含实现代码, 文中的 Python 片段只用来固定接口形状
方案挂进 `docs/messaging-plugins.md` 第 2 节的统一抽象, 实现类继承 `server/src/hx_email/server/messaging/types.py` 中的 `MessagingAdapter` 这个抽象基类
分层遵循 `docs/adr/0001-fastapi-react-rewrite-with-deep-modules.md`, 路由保持薄层, 签名校验, 去重, token 管理与事件映射全部收敛在 GitHub provider 这个深模块内部
文中凡标注 "需复核" 的数字或行为, 都来自 GitHub 公开文档的既有认知, 落地前必须对照 docs.github.com 当前版本再确认一次

## 0. 需求来源

用户提出两点要求, 第一点是 GitHub 侧使用 GitHub App 这种方案来做
第二点是覆盖 GitHub 的消息监听与消息发送
在本方案里, "一条消息" 指 issue 与 pull request 线程上出现的一次可读文字事件, 例如一条评论, 一次新建, 一次 review 提交

## 1. 为什么必须用 GitHub App 而不是 PAT

### 1.1 身份与权限

- GitHub App 以独立的 bot 身份行动, 评论作者显示为 `<app-slug>[bot]`, 与任何个人账号解耦
- App 的权限在创建时逐项声明, 安装时由仓库所有者确认, 可以最小化到 "只装在一个仓库, 只订阅几个事件" 这样的粒度
- App 调 API 时使用 installation token, 它只在被安装的仓库范围内有效, 范围之外的仓库一律 404
- PAT 代表一个真实用户, classic PAT 的 scope 粒度很粗, 一个 `repo` scope 就覆盖该用户能访问的全部私有仓库
- fine-grained PAT 虽然可以限仓限权, 但仍然绑定个人身份, 用户离职或账号被封会让整条链路一起失效

### 1.2 生命周期与泄漏面

- installation token 有效期为 1 小时, 过期后由服务端用 App 私钥重新签发, 全程无需人工介入
- 即使某个 installation token 泄漏, 攻击窗口最长 1 小时, 且只覆盖该 installation 的仓库与已授权的权限
- PAT 通常设置为长期有效或数月有效, 一旦泄漏, 攻击者拿到的是该用户的全部能力, 属于全盘失守
- App 私钥可以在 App 设置页随时吊销并重新生成, 吊销后所有派生 token 立即无法续签

### 1.3 Webhook 与配额

- GitHub App 自带一个 App 级 webhook, 所有安装仓库的事件都投递到同一个地址, 不需要逐仓手工配置 webhook
- PAT 方案要么在每个仓库手工建 webhook, 要么轮询 API, 前者运维成本高, 后者浪费配额且有延迟
- App 的 installation 拥有独立于任何个人用户的速率配额, 不会与用户自己的脚本或 CI 抢配额

### 1.4 速率上限对比 (需复核)

| 身份                                   | REST 主速率上限 (每小时)                                     | 说明                       |
| -------------------------------------- | ------------------------------------------------------------ | -------------------------- |
| PAT (classic 或 fine-grained)          | 5000                                                         | 与该用户所有其他调用共享   |
| GitHub App installation token          | 基线 5000, 仓库数超过 20 后每多一个仓库加 50, 封顶 12500     | 按 installation 计, 不按人 |
| 安装在 GitHub Enterprise Cloud 组织上  | 15000                                                        | 仅企业组织                 |
| App 自身 JWT 调用 (如 `GET /app`)      | 与 installation 配额分开计                                   | 只用于签 token 与查安装    |

- 以上数字均需复核, 来源为 GitHub 文档 "Rate limits for the REST API" 一节
- 两种身份都受二级速率限制约束, 例如单位时间内创建内容的次数上限, 具体阈值需复核, 实现上统一按响应头处理而不是硬编码数字

## 2. GitHub App 的创建与配置步骤

### 2.1 创建步骤

1. 在 GitHub 个人或组织的 Settings, 进入 Developer settings, 选择 GitHub Apps, 点击 New GitHub App
2. 填写 App 名称, 名称会决定 slug, 进而决定 bot 登录名 `<app-slug>[bot]`, 这个登录名后面用于防回环
3. Homepage URL 填 HX-Email 实例的公网地址即可
4. Webhook 勾选 Active, Webhook URL 填 `https://<公网域名>/api/v1/messaging/events/github/<instance_slug>`, 其中 `instance_slug` 见第 5 节
5. Webhook secret 填一个至少 32 字节的随机串, 由 HX-Email 在创建实例时生成并展示一次, 用户复制到 GitHub
6. 按 2.2 节逐项设置 Repository permissions, 其余权限保持 No access
7. 按第 3 节在 Subscribe to events 中只勾选需要的事件
8. "Where can this GitHub App be installed" 默认选 Only on this account, 避免被陌生账号安装
9. 创建后记录 App ID 与 Client ID, 并点击 Generate a private key 下载 PEM 私钥
10. 在 App 页面点击 Install App, 选择 Only select repositories, 只勾选需要接入的仓库
11. 把 App ID, Client ID, 私钥 PEM, webhook secret 填入 HX-Email 的 GitHub 实例配置, 服务端整体加密落库

### 2.2 权限最小集 (逐条说明)

| 权限 (Repository permissions) | 级别         | 阶段        | 为什么需要                                                                                         |
| ----------------------------- | ------------ | ----------- | -------------------------------------------------------------------------------------------------- |
| Metadata                      | Read-only    | 第一阶段起  | GitHub 对所有 App 强制要求, 用于读取仓库基本信息, 解析 `owner/repo` 与 installation 的对应关系     |
| Issues                        | Read & write | 第一阶段起  | 订阅 `issues` 与 `issue_comment` 事件的前提, 也是发 issue 评论, 开 issue, 关 issue, 加标签所需权限 |
| Pull requests                 | Read & write | 第一阶段起  | 订阅 `pull_request`, `pull_request_review`, `pull_request_review_comment` 事件, 并回复 review 评论 |
| Contents                      | Read-only    | 第三阶段可选 | 只有开启 `push` 事件订阅时才需要, 用于接收推送事件与读取提交信息, 不开 push 就不申请               |

- Issues 写权限同时覆盖 PR 主线程上的普通评论, 因为 PR 主线程评论走的是 issue comments 接口, 这一点需复核
- 加标签走 issue labels 接口, 依赖 Issues 写权限, 对 PR 加标签同样走 issue 接口, 需复核
- 第一阶段若只做 issue 评论, Pull requests 可以先降为 Read-only, 但为了能回复 review 评论, 推荐第一阶段直接给 Read & write

### 2.3 一律不申请的权限

- Administration, 仓库设置与协作者管理, 与收发消息无关, 申请即扩大破坏面
- Contents 写权限, App 永远不改代码, 不推提交, 不建分支
- Workflows 与 Actions, 不触发也不修改 CI
- Secrets, Variables, Environments, Deployments, 涉及凭据与发布, 绝不申请
- Checks, Commit statuses, Pages, Packages, Codespaces, 与消息无关
- Organization permissions 全部 No access, 包括 Members 与 Administration
- Account permissions 全部 No access, App 不代表任何个人用户读写邮箱或资料
- 任何 "User-to-server" 授权流程在本方案中都不启用, App 只用 installation 身份行动

## 3. 事件订阅清单与 envelope 映射

### 3.1 订阅的事件

| 事件 (X-GitHub-Event)         | 关心的 action                                            | 阶段     | 是否算一条消息                 |
| ----------------------------- | -------------------------------------------------------- | -------- | ------------------------------ |
| `issue_comment`               | created, edited                                          | 第一阶段 | 是, issue 与 PR 主线程上的评论 |
| `pull_request_review_comment` | created, edited                                          | 第一阶段 | 是, PR 代码行内评论            |
| `issues`                      | opened, closed, reopened, labeled                        | 第二阶段 | opened 是, 其余为状态类消息    |
| `pull_request`                | opened, closed, reopened, ready_for_review, synchronize  | 第二阶段 | opened 是, 其余为状态类消息    |
| `pull_request_review`         | submitted                                                | 第二阶段 | 是, review 总结与结论          |
| `push`                        | 无 action 字段                                           | 第三阶段 | 可选, 作为频道型通知           |
| `installation`                | created, deleted, suspend, unsuspend                     | 第一阶段 | 否, 只更新 installation 缓存   |
| `installation_repositories`   | added, removed                                           | 第一阶段 | 否, 只更新仓库到安装的映射     |

- `installation` 与 `installation_repositories` 无需在订阅页勾选, GitHub 会默认投递给 App, 需复核
- 未列出的事件与未列出的 action 一律返回 2xx 后丢弃, 不入库
- `issue_comment` 的 deleted 与 edited 只在第二阶段以后才转成消息, 第一阶段 edited 只更新已有记录的 text

### 3.2 会话标识约定

- issue 或 PR 线程: `chat_id = "<owner>/<repo>#<number>"`, `chat_type = "group"`, 因为线程是多人参与的会话
- 仓库推送流: `chat_id = "<owner>/<repo>@<ref>"`, `chat_type = "channel"`, 因为它是只读广播
- 不引入新的 `chat_type` 取值, 现有 `ChatType = Literal["private", "group", "channel"]` 已经足够, 也避免改动 types.py
- issue 与 PR 共用 `#<number>` 编号空间, 同一仓库内不会冲突, 是否是 PR 写在 `raw["gh_thread_kind"]` 这个键里

### 3.3 字段映射表

统一信封为现有 `MessagingMessage`, 所有 GitHub 专有信息放进 `raw`, 不扩展 dataclass 字段

| envelope 字段 | `issue_comment`                        | `pull_request_review_comment`          | `issues` opened                 | `pull_request` 各 action        | `pull_request_review` submitted     | `push`                            |
| ------------- | -------------------------------------- | -------------------------------------- | ------------------------------- | ------------------------------- | ----------------------------------- | --------------------------------- |
| direction     | `"inbound"`                            | `"inbound"`                            | `"inbound"`                     | `"inbound"`                     | `"inbound"`                         | `"inbound"`                       |
| chat_id       | `repo.full_name#issue.number`          | `repo.full_name#pull_request.number`   | `repo.full_name#issue.number`   | `repo.full_name#number`         | `repo.full_name#pull_request.number` | `repo.full_name@ref`              |
| chat_type     | `"group"`                              | `"group"`                              | `"group"`                       | `"group"`                       | `"group"`                           | `"channel"`                       |
| sender_id     | `str(comment.user.id)`                 | `str(comment.user.id)`                 | `str(issue.user.id)`            | `str(sender.id)`                | `str(review.user.id)`               | `str(sender.id)`                  |
| sender_name   | `comment.user.login`                   | `comment.user.login`                   | `issue.user.login`              | `sender.login`                  | `review.user.login`                 | `pusher.name`                     |
| text          | `comment.body`                         | `comment.body`                         | `issue.title` 加空行加 `issue.body` | opened 为标题加正文, 其余为状态句 | `review.state` 加 `review.body`  | 每个 commit 的 message 首行拼接   |
| message_id    | `"ic:" + comment.id`                   | `"rc:" + comment.id`                   | `"is:" + issue.id`              | `"pr:" + pull_request.id + ":" + action` | `"rv:" + review.id`        | `"push:" + after`                 |
| created_at    | `comment.created_at`                   | `comment.created_at`                   | `issue.created_at`              | `pull_request.updated_at`       | `review.submitted_at`               | `head_commit.timestamp`           |
| raw           | 见下方 raw 约定                        | 同左, 另含 `path`, `line`, `in_reply_to_id` | 同左, 另含 `labels`         | 同左, 另含 `action`, `merged`   | 同左, 另含 `state`                  | 同左, 另含 `commits` 数量         |

- raw 约定: 至少包含 `gh_event`, `gh_action`, `gh_delivery`, `gh_installation_id`, `gh_repo_id`, `gh_thread_kind`, `html_url`, `sender_type` 这些键
- raw 不存整个 payload, 只存上面这些键与少量事件专有键, 控制单条消息体积
- `message_id` 带类型前缀, 保证不同对象类型的数字 ID 不会撞车, 也让 edited 事件可以按同一 `message_id` 覆盖 text
- 所有 created_at 保留 GitHub 给出的 ISO 8601 UTC 字符串, 不做时区转换
- 状态类消息的 text 用固定模板生成, 例如 "PR #12 closed (merged)", 模板放在 provider 模块内部

### 3.4 防回环

- 若 `sender.type == "Bot"` 且 `sender.login == "<app-slug>[bot]"`, 事件仍记录 delivery, 但以 `direction = "outbound"` 入库或直接丢弃, 不触发任何自动回复
- 本 App 发出的评论正文末尾带隐藏标记 `<!-- hx-email op=<op_id> -->`, 入站映射时识别这个标记, 作为第二道防线

## 4. 发送侧写入动作清单

所有写入动作都由 `GitHubWriteAction` 描述, 通用文本回复走 `send_message`, 其余走 `perform`, 见第 8 节

| 动作         | REST 接口                                                             | 最小权限              | 幂等处理                                                                 | 失败重试                                   |
| ------------ | --------------------------------------------------------------------- | --------------------- | ------------------------------------------------------------------------ | ------------------------------------------ |
| 发 issue 评论 | `POST /repos/{owner}/{repo}/issues/{number}/comments`                | Issues: write         | 正文尾部写入 `op_id` 隐藏标记, 超时后先列最近评论查标记, 命中即视为成功 | 按 4.2 通用策略, 查标记后才允许重发        |
| 发 PR 评论 (主线程) | 同上, PR 号作为 number                                         | Issues: write 或 Pull requests: write, 需复核 | 同上                                                  | 同上                                       |
| 回复 PR 行内评论 | `POST /repos/{owner}/{repo}/pulls/{number}/comments/{comment_id}/replies` | Pull requests: write | 同上, 查重范围为该 PR 的 review comments                              | 同上                                       |
| 开 issue     | `POST /repos/{owner}/{repo}/issues`                                   | Issues: write         | 正文尾部写入 `op_id` 标记, 重发前按 `creator=<app-slug>[bot]` 与 `since` 列 issue 查标记 | 同上                         |
| 关闭 issue   | `PATCH /repos/{owner}/{repo}/issues/{number}`, body 为 `state=closed` | Issues: write         | 天然幂等, 重复关闭结果相同, 可附 `state_reason`                          | 直接按 4.2 重试                            |
| 加标签       | `POST /repos/{owner}/{repo}/issues/{number}/labels`                   | Issues: write         | 天然幂等, 已存在的标签再加一次不产生变化, 需复核                         | 直接按 4.2 重试, 422 不重试                |

### 4.1 op_id 与本地发件记录

- 每个写入动作在调用 GitHub 之前生成 `op_id` (uuid4), 并以 `direction = "outbound"` 预写一条消息记录, 状态记在 raw 的 `gh_send_state` 中
- 调用成功后回填 `message_id` 为 GitHub 返回的对象 ID, 状态改为 sent
- 进程崩溃导致状态停在 pending 时, 恢复流程按 op_id 去 GitHub 查标记, 查到就回填, 查不到才重发
- 对调用方返回的 `send_message` 结果是 GitHub 对象 ID 的字符串, 与 QQ 返回平台消息 ID 的语义一致

### 4.2 通用重试策略

- 网络错误, 超时, 5xx: 指数退避 1 秒, 2 秒, 4 秒, 最多 3 次, 非天然幂等的动作每次重发前先做标记查重
- 401: 视为 installation token 失效, 强制刷新 token 后重试 1 次, 仍失败则把实例状态置为 error
- 403 或 429 且带 `Retry-After`: 按该头等待后重试, 等待上限 5 分钟, 超过则放弃并记录
- 403 且 `X-RateLimit-Remaining` 为 0: 等到 `X-RateLimit-Reset` 指示的时间点, 期间该 installation 的写入进入队列
- 二级速率限制且没有 `Retry-After`: 至少等待 60 秒, 需复核
- 404, 410, 422: 不重试, 直接返回 `MessagingError`, 常见原因是仓库不在安装范围或 issue 已锁定
- 同一 installation 的写入串行执行, 避免触发内容创建类二级限流

## 5. Webhook 接收实现要点

### 5.1 路由与实例定位

- 路由为 `POST /api/v1/messaging/events/github/{instance_slug}`, `instance_slug` 是创建实例时生成的随机串, 只用于定位实例, 不作为鉴权凭据
- GitHub 无法携带自定义头, 所以 GitHub 实例不使用现有的 `X-Messaging-Token` 鉴权, 改由签名校验完成鉴权
- 路由层只做三件事, 读取原始 body 字节, 收集请求头, 调用 provider 的 `handle_webhook`, 其余逻辑全部在 provider 内部
- 这个路由需要在现有 `/events/{kind}` 旁边新增, 由负责 server/ 实现的一方落地, 本文只给出契约
- 请求头 `X-GitHub-Hook-Installation-Target-ID` 应等于实例配置中的 App ID, 不一致直接拒绝, 这个头的名称需复核

### 5.2 X-Hub-Signature-256 校验流程

1. 读取原始请求体字节, 在任何 JSON 解析之前完成校验, 不允许对 body 重新序列化
2. 取请求头 `X-Hub-Signature-256`, 缺失或不以 `sha256=` 开头时返回 401
3. 用实例配置中的 webhook secret (UTF-8 字节) 作为密钥, 对原始 body 计算 HMAC-SHA256, 得到十六进制小写摘要
4. 把 `"sha256=" + 摘要` 与请求头整体做常量时间比较 (`hmac.compare_digest`), 不相等返回 401
5. 不接受旧的 `X-Hub-Signature` (SHA-1) 头作为替代, 只认 SHA-256
6. 校验通过后才解析 JSON, 解析失败返回 400
7. 支持 secret 轮换, 配置中允许同时保存 current 与 previous 两个 secret, 任一匹配即通过, 轮换完成后删除 previous

### 5.3 去重与重投递

- 去重键为请求头 `X-GitHub-Delivery` 的 GUID, 它在一次投递中全局唯一
- 新增表 `messaging_webhook_deliveries`, 主键为 `(instance_id, delivery_id)`, 字段含 `event`, `action`, `received_at`, `status`, `payload_encrypted` 这些字段
- 签名通过后先尝试插入该表, 主键冲突说明是重复投递, 直接返回 200 且不再处理
- 手动或通过 API 触发的重投递沿用原 GUID, 因此会被这张表挡住, 这一行为需复核
- GitHub 不会自动重试失败的投递, 失败的投递需要通过 App 的 deliveries 接口主动拉取并重投, 需复核
- 第二道去重为消息层的 `message_id`, 同一实例同一 `message_id` 的入站消息只保留一条, edited 事件覆盖 text
- 去重表保留 7 天, 由已有的定时清理任务或启动时清理删除过期行

### 5.4 响应时间

- GitHub 要求在 10 秒内返回响应, 超时即记为投递失败, 需复核
- 本方案目标为 500 毫秒内返回, 同步路径只包含签名校验, 去重插入, 原始 payload 加密落盘三步
- 成功入队返回 202, 重复投递返回 200, 签名错误返回 401, 未订阅事件返回 204
- 异步处理由进程内单个工作线程消费, 负责事件映射, 写入 `messaging_messages`, 更新 installation 缓存
- 进程重启时扫描去重表中 `status = "pending"` 的行重新处理, 保证已返回 2xx 的投递不会丢失

### 5.5 本地开发打通

- 方案一使用 smee: 在 smee.io 新建一个 channel, 把 channel URL 填为 App 的 Webhook URL, 本地运行 `npx smee-client --url <channel> --target http://127.0.0.1:8000/api/v1/messaging/events/github/<instance_slug>` 这个地址
- smee 客户端转发时可能重新序列化 JSON, 导致签名校验失败, 需复核, 若遇到此问题改用方案二
- 方案二使用 cloudflared 快速隧道: 运行 `cloudflared tunnel --url http://127.0.0.1:8000`, 把得到的 trycloudflare 地址拼上路由路径填入 App, 原始 body 不被改写
- 本地开发建议单独建一个开发用 App, 只安装到一个测试仓库, 与正式 App 的私钥和 secret 完全隔离
- App 设置页的 Advanced 标签可以查看每次投递的请求与响应, 并手动 Redeliver, 用来回放调试

## 6. Installation token 生命周期管理

### 6.1 签发链路

1. 用 App 私钥签 RS256 JWT, `iat` 取当前时间减 60 秒以抵消时钟偏差, `exp` 取当前时间加 9 分钟, JWT 最长有效期为 10 分钟, 需复核
2. JWT 的 `iss` 填 Client ID, GitHub 也接受 App ID, 需复核
3. 用 JWT 调 `POST /app/installations/{installation_id}/access_tokens`, 得到 `token` 与 `expires_at` 两个字段
4. 签发时可在请求体中进一步收窄 `repositories` 与 `permissions`, 写入动作默认收窄到目标仓库

### 6.2 何时刷新

- 每个 token 在内存中记录 `expires_at`, 使用前若剩余有效期少于 5 分钟则先刷新
- 调 API 返回 401 时强制刷新一次, 防止 token 被提前吊销
- 同一 installation 的刷新加单飞锁, 并发请求只触发一次签发, 其余等待结果
- 空闲时不做任何定时刷新, token 过期就让它过期, 下次真正要调 API 时再签, 这是空闲零开销的关键

### 6.3 缓存在哪

- 第一层为进程内字典 `dict[int, InstallationToken]`, 键为 installation_id, 生命周期与 adapter 实例一致
- 第二层为加密持久化, 用于进程重启后避免立即重签, 存入新增表 `messaging_github_tokens`, 每个 installation 一行
- 持久化是可选优化, 签一次 token 只是一次 HTTP 调用, 若希望进一步缩小泄漏面, 可以只保留内存缓存

### 6.4 加密存储

- App 私钥 PEM, webhook secret, App ID, Client ID 一起放进实例配置 JSON, 经 `security.encrypt_secret` 整体加密写入 `messaging_instances.config_encrypted`, 与 QQ 实例完全同一路径
- installation token 写入 `messaging_github_tokens.token_encrypted` 前同样调用 `encrypt_secret`, 读取时调用 `decrypt_secret` 还原明文
- 任何 API 返回中, 私钥, secret, token 一律脱敏为 `***`, 与现有 event_token 的脱敏规则一致
- 日志中只打印 token 的前 4 位与 `expires_at`, 不打印完整 token 与 JWT
- 去重表中的原始 payload 也经 `encrypt_secret` 加密, 因为私有仓库的评论正文属于敏感内容

### 6.5 多 installation 时如何选择

- 一个 HX-Email 实例对应一个 GitHub App, 一个 App 可以有多个 installation, 例如个人账号一个, 组织一个
- 入站事件直接使用 payload 中的 `installation.id`, 回复时沿用该 ID, 不需要查询
- 主动发送时根据 `chat_id` 中的 `owner/repo` 查映射表 `repo_full_name -> installation_id`, 映射由 `installation` 与 `installation_repositories` 事件维护
- 映射缺失时调 `GET /repos/{owner}/{repo}/installation` (JWT 身份) 查询并写回缓存, 返回 404 说明 App 未安装到该仓库, 直接报错
- installation 被 suspend 或 deleted 时从映射中移除, 并清除对应 token 缓存

## 7. 内存与 CPU

### 7.1 目标值

- 空闲时 CPU 占用目标为 0, 没有轮询线程, 没有心跳, 没有长连接
- 空闲时内存增量目标为不超过 10 MB, 主要是 adapter 对象, installation 映射与少量 token 缓存
- 单个 webhook 的同步路径 CPU 耗时目标为 5 毫秒以内 (不含网络与磁盘), 异步映射目标为 20 毫秒以内
- 以上为设计目标值, 落地后用 `ps -o rss` 与压测脚本实测, 偏差超过一倍需要回到本文调整设计

### 7.2 为什么天然比 QQ 侧低

- QQ 侧需要常驻一个 NapCat 容器, 内部运行真实 NTQQ 客户端与 Xvfb, 内存占用为数百 MB, 且有持续的心跳与协议保活
- GitHub 侧没有任何常驻协议端, 消息由 GitHub 主动推送到已有的 FastAPI 进程, 复用现有 HTTP 服务与数据库连接
- token 按需签发, 不需要像 QQ 登录态那样持续维持
- 发送是一次普通 HTTPS 请求, 不需要维护会话状态机, 因此这条链在没有事件时等于不存在

## 8. 与路由层的接口契约

### 8.1 能力位

```python
GITHUB_CAPABILITIES: Capabilities = Capabilities(
    supports_qr_login=False,
    supports_groups=True,
    supports_history=True,
    risk_level="official",
    risk_notice="使用官方 GitHub App, 无封号风险, 权限按最小集申请",
)
```

- `supports_groups=True` 表示 `list_groups` 返回已安装仓库列表, `group_action` 在本 provider 中不支持, 抛出 `MessagingError` 异常
- 注册方式与 QQ 一致, 在 `registry.PLUGIN_KINDS` 中新增 `PluginKind(key="github", ...)`, `adapter_factory` 指向下面的类

### 8.2 provider 必须实现的方法

```python
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from hx_email.config import Settings
from hx_email.server.messaging.types import (
    AdapterStatus, Capabilities, LoginState, LoginTicket, MessageTarget,
    MessagingAdapter, MessagingConversation, MessagingGroup, MessagingInstance, MessagingMessage,
)

WebhookStatus = Literal["accepted", "duplicate", "ignored", "rejected"]
WriteKind = Literal["comment", "reply_review_comment", "open_issue", "close_issue", "add_labels"]


@dataclass(frozen=True)
class InstallationToken:
    installation_id: int
    token: str
    expires_at: datetime
    repository_ids: tuple[int, ...] = ()
    permissions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WebhookOutcome:
    status: WebhookStatus
    http_status: int
    delivery_id: str = ""
    event: str = ""
    reason: str = ""


@dataclass(frozen=True)
class GitHubWriteAction:
    kind: WriteKind
    repo_full_name: str
    op_id: str
    number: int | None = None
    body: str = ""
    title: str = ""
    labels: tuple[str, ...] = ()
    reply_to_comment_id: int | None = None
    state_reason: Literal["completed", "not_planned"] | None = None


@dataclass(frozen=True)
class GitHubWriteResult:
    op_id: str
    object_id: str
    html_url: str
    deduplicated: bool = False


class GitHubAppAdapter(MessagingAdapter):
    kind: str = "github"
    display_name: str = "GitHub"
    capabilities: Capabilities = GITHUB_CAPABILITIES

    def __init__(self, settings: Settings, instance: MessagingInstance) -> None: ...

    # 统一接口, 与 QQ provider 完全同签名
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def status(self) -> AdapterStatus: ...
    def create_login(self) -> LoginTicket: ...
    def check_login(self) -> LoginState: ...
    def send_message(self, target: MessageTarget, text: str) -> str: ...
    def list_conversations(self) -> list[MessagingConversation]: ...
    def list_messages(self, conversation_id: str, limit: int = 50) -> list[MessagingMessage]: ...
    def list_groups(self) -> list[MessagingGroup]: ...

    # GitHub 专有, 路由层只在 kind == "github" 时调用
    def handle_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookOutcome: ...
    def perform(self, action: GitHubWriteAction) -> GitHubWriteResult: ...
    def installation_token(self, installation_id: int, *, force_refresh: bool = False) -> InstallationToken: ...


def verify_signature(secrets: tuple[bytes, ...], body: bytes, header_value: str | None) -> bool: ...
```

### 8.3 统一接口在 GitHub 上的语义

- `start`: 用 JWT 调 `GET /app` 验证私钥有效, 再调 `GET /app/installations` 预热 installation 映射, 不启动任何线程
- `stop`: 清空内存 token 缓存与映射, 停止异步工作线程中属于本实例的任务
- `status`: `state` 为 online 表示 JWT 校验通过且至少有一个 installation, `account_name` 为 `<app-slug>[bot]` 这个登录名
- `create_login`: 返回 `LoginTicket(mode="github_app_install", url="https://github.com/apps/<app-slug>/installations/new")`, 引导用户安装 App
- `check_login`: 至少存在一个未 suspend 的 installation 时 `logged_in=True` 的状态
- `send_message`: `target.chat_id` 必须形如 `owner/repo#number` 且 `chat_type == "group"`, 内部转成 `GitHubWriteAction(kind="comment")` 交给 `perform`, 返回评论 ID 字符串
- `list_conversations`: 返回本地已入库的线程, 按最近消息时间倒序, 不实时调 GitHub, 避免消耗配额
- `list_messages`: 先返回本地记录, 本地为空时调 issue comments 接口回填最近 `limit` 条
- `list_groups`: 返回各 installation 可访问的仓库, `group_id` 为 `owner/repo` 这种格式
- `group_action`: 沿用基类默认实现, 抛出 `MessagingError`, API 层按现有约定返回 501

### 8.4 与 QQ provider 必须一致的字段

- `MessagingMessage` 的 `direction`, `chat_id`, `chat_type`, `sender_id`, `sender_name`, `text`, `message_id`, `created_at`, `raw` 九个字段名与类型完全一致
- `direction` 只取 `"inbound"` 或 `"outbound"`, `chat_type` 只取现有三个字面量
- `sender_id` 与 `message_id` 一律为字符串, 即使 GitHub 原始值是整数
- `MessageTarget` 只用 `chat_id` 与 `chat_type`, 不添加 GitHub 专有字段, 专有参数通过 `perform` 传入
- `send_message` 返回平台对象 ID 的字符串, 失败抛 `MessagingError`, 与 QQ 行为一致
- `AdapterStatus.state` 只取 `stopped`, `connecting`, `online`, `error` 四个取值
- 入库统一调用 `store.save_message`, 不为 GitHub 另建消息表, REST 查询接口对前端完全透明

### 8.5 配置键

- `app_id`, `client_id`, `app_slug`, `private_key_pem`, `webhook_secret`, `webhook_secret_previous`, `instance_slug` 这七个键
- 全部为字符串, 与现有 `MessagingInstance.config: dict[str, str]` 的类型约束一致

## 9. 分阶段落地

### 9.1 第一阶段: issue 与 PR 评论的监听与回复

- 范围: 订阅 `issue_comment` 与 `pull_request_review_comment` 两个事件的 created 与 edited, 外加 installation 生命周期事件
- 权限: Metadata 只读, Issues 读写, Pull requests 读写
- 交付: webhook 路由, 签名校验, delivery 去重表, 异步入库, installation token 管理, `send_message` 回复评论, 回复 PR 行内评论
- 验收: 在测试仓库发一条 issue 评论, 5 秒内出现在 HX-Email 消息列表, 从 HX-Email 回复后在 GitHub 上看到 bot 评论, 且不触发回环
- 验收: 在 App 设置页对同一投递点击 Redeliver, 消息表中不出现重复记录
- 验收: 用错误 secret 签名的请求返回 401 且不入库

### 9.2 第二阶段: 线程状态与更多写入动作

- 增加 `issues`, `pull_request`, `pull_request_review` 事件, 生成状态类消息
- 增加开 issue, 关闭 issue, 加标签三个写入动作, 前端以线程内操作菜单的形式暴露
- 增加 deliveries 接口的补投巡检, 仅在用户手动触发时执行, 不引入常驻轮询

### 9.3 第三阶段: 可选能力

- 可选订阅 `push`, 此时才申请 Contents 只读, 推送消息以 `channel` 会话呈现
- 支持多个 App 实例并存, 例如工作组织与个人账号各一个 App
- 支持 webhook secret 在线轮换与私钥轮换的引导页面

## 10. 风险与需复核事项汇总

- 第 1.4 节全部速率数字需复核
- PR 主线程评论所需权限是 Issues 写还是 Pull requests 写即可, 需复核
- 重投递是否沿用原 `X-GitHub-Delivery` GUID, 需复核
- GitHub 是否会自动重试失败投递, 需复核
- 10 秒响应时限与 JWT 10 分钟有效期, 需复核
- `X-GitHub-Hook-Installation-Target-ID` 请求头名称, 需复核
- smee 客户端是否改写 body 导致签名失败, 需复核
- 评论正文长度上限 (约 65536 字符), 需复核, 超长时 provider 截断并在末尾标注已截断
