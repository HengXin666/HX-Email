# GitHub Provider 接入方案 (GitHub App)

本文给出 HX-Email 消息插件体系中 GitHub 侧消息监听与发送的接入方案
本文只是设计文档, 不含实现代码, 文中的 Python 片段只用来固定接口形状
会话地址, envelope, 幂等, 重试, 限流与保留期以 `docs/messaging-router.md` 为准, 本文只说明 GitHub provider 如何实现这些契约, 两者冲突时以规格为准
方案分两块: 路由层使用的 provider 实现 ADR 0005 第 4 节的 `MessagingProvider` 协议; 实例管理与旧前端沿用 `docs/messaging-plugins.md` 第 2 节的统一抽象, 由一个继承 `MessagingAdapter` 的类承担
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

| 身份                                  | REST 主速率上限 (每小时)                                 | 说明                       |
| ------------------------------------- | -------------------------------------------------------- | -------------------------- |
| PAT (classic 或 fine-grained)         | 5000                                                     | 与该用户所有其他调用共享   |
| GitHub App installation token         | 基线 5000, 仓库数超过 20 后每多一个仓库加 50, 封顶 12500 | 按 installation 计, 不按人 |
| 安装在 GitHub Enterprise Cloud 组织上 | 15000                                                    | 仅企业组织                 |
| App 自身 JWT 调用 (如 `GET /app`)     | 与 installation 配额分开计                               | 只用于签 token 与查安装    |

- 以上数字均需复核, 来源为 GitHub 文档 "Rate limits for the REST API" 一节
- 两种身份都受二级速率限制约束, 例如单位时间内创建内容的次数上限, 具体阈值需复核, 实现上统一按响应头处理而不是硬编码数字

## 2. GitHub App 的创建与配置步骤

### 2.1 创建步骤

1. 在 GitHub 个人或组织的 Settings, 进入 Developer settings, 选择 GitHub Apps, 点击 New GitHub App
2. 填写 App 名称, 名称会决定 slug, 进而决定 bot 登录名 `<app-slug>[bot]`, 这个登录名后面用于防回环
3. Homepage URL 填 HX-Email 实例的公网地址即可
4. Webhook 勾选 Active, Webhook URL 填 `https://<公网域名>/api/v1/router/ingress/github/<instance_id>`, 其中 `instance_id` 见第 5.1 节
5. Webhook secret 填一个至少 32 字节的随机串, 由 HX-Email 在创建实例时生成并展示一次, 用户复制到 GitHub
6. 按 2.2 节逐项设置 Repository permissions, 其余权限保持 No access
7. 按第 3 节在 Subscribe to events 中只勾选需要的事件
8. "Where can this GitHub App be installed" 默认选 Only on this account, 避免被陌生账号安装
9. 创建后记录 App ID 与 Client ID, 并点击 Generate a private key 下载 PEM 私钥
10. 在 App 页面点击 Install App, 选择 Only select repositories, 只勾选需要接入的仓库
11. 把 App ID, Client ID, App slug, 私钥 PEM, webhook secret 填入 HX-Email 的 GitHub 实例配置, 服务端整体加密落库

### 2.2 权限最小集 (逐条说明)

| 权限 (Repository permissions) | 级别         | 阶段          | 为什么需要                                                                                         |
| ----------------------------- | ------------ | ------------- | -------------------------------------------------------------------------------------------------- |
| Metadata                      | Read-only    | 第一阶段起    | GitHub 对所有 App 强制要求, 用于读取仓库基本信息, 解析 `owner/repo` 与 installation 的对应关系     |
| Issues                        | Read & write | 第一阶段起    | 订阅 `issues` 与 `issue_comment` 事件的前提, 也是发 issue 评论, 开 issue, 关 issue, 加标签所需权限 |
| Pull requests                 | Read & write | 第一阶段起    | 订阅 `pull_request`, `pull_request_review`, `pull_request_review_comment` 事件, 并回复 review 评论 |
| Contents                      | Read-only    | 2026-11-08 起 | 订阅 `push` 与 `commit_comment` 的前提; 只读, App 仍不改代码, 不推提交, 不建分支                   |
| Discussions                   | Read-only    | 2026-11-08 起 | 订阅 `discussion` 与 `discussion_comment`; 在 discussion 下回复时再升为 Read & write               |

- Issues 写权限同时覆盖 PR 主线程上的普通评论, 因为 PR 主线程评论走的是 issue comments 接口, 这一点需复核
- 加标签走 issue labels 接口, 依赖 Issues 写权限, 对 PR 加标签同样走 issue 接口, 需复核
- 第一阶段只做入站时 Pull requests 可以先降为 Read-only, 第二阶段开始回复行内评论前必须改为 Read & write, 推荐一开始直接给 Read & write, 避免中途让仓库所有者重新确认权限

### 2.3 一律不申请的权限

- Administration, 仓库设置与协作者管理, 与收发消息无关, 申请即扩大破坏面
- Contents 写权限不申请: App 永远不改代码, 不推提交, 不建分支 (只读权限见 2.2, 用于收 `push` 与 `commit_comment`)
- 已安装的 App 升级到 2.2 的权限后, 仓库所有者要在 GitHub 上确认一次新权限, 否则这四类事件不会投递
- Workflows 与 Actions, 不触发也不修改 CI
- Secrets, Variables, Environments, Deployments, 涉及凭据与发布, 绝不申请
- Checks, Commit statuses, Pages, Packages, Codespaces, 与消息无关
- Organization permissions 全部 No access, 包括 Members 与 Administration
- Account permissions 全部 No access, App 不代表任何个人用户读写邮箱或资料
- 任何 "User-to-server" 授权流程在本方案中都不启用, App 只用 installation 身份行动

## 3. 事件订阅清单与 envelope 映射

### 3.1 订阅的事件

事件集与规格第 3.4 节和 ADR 0005 第 7 节一致, 全部在第一阶段订阅

| 事件 (X-GitHub-Event)         | 关心的 action                              | 是否算一条消息                                                       |
| ----------------------------- | ------------------------------------------ | -------------------------------------------------------------------- |
| `issue_comment`               | created, edited                            | 是, issue 与 PR 主线程上的评论                                       |
| `pull_request_review_comment` | created, edited                            | 是, PR 代码行内评论                                                  |
| `pull_request_review`         | submitted                                  | 是, review 结论与正文                                                |
| `issues`                      | opened, closed, reopened                   | opened 是普通消息, 其余为状态消息                                    |
| `pull_request`                | opened, closed, reopened, ready_for_review | opened 是普通消息, 其余为状态消息                                    |
| `discussion`                  | created                                    | 是, 新开 discussion; 其它 action 只更新会话元数据                    |
| `discussion_comment`          | created, edited                            | 是, discussion 下的评论, 回复带 `reply_to`                           |
| `commit_comment`              | created                                    | 是, 提交上的评论 (含行内)                                            |
| `push`                        | 无 action                                  | 每个 distinct 提交一条消息, 删分支与重复提交不产消息, 每次最多 20 条 |
| `installation`                | created, deleted, suspend, unsuspend       | 否, 只更新 installation 缓存                                         |
| `installation_repositories`   | added, removed                             | 否, 只更新仓库到安装的映射                                           |

- `installation` 与 `installation_repositories` 无需在订阅页勾选, GitHub 会默认投递给 App, 需复核, 复核方法是新建开发用 App 后安装到测试仓库并在 Advanced 页查看是否收到这两类投递
- `push` 与 `commit_comment` 需要 Contents 只读, discussion 两类需要 Discussions 只读, 见 2.2
- 应用一键创建 (manifest) 默认勾选以上全部事件与权限
- 未列出的事件与未列出的 action 一律返回 2xx 后丢弃, 不入库
- edited 只覆盖同一 `dedup_key` 已有记录的 `text`, 不新增消息

### 3.2 会话标识约定

会话使用规格第 2 节的统一 session 地址, 写入 `messaging_messages.chat_id`

| 会话                                  | 地址                                                      | 示例                                     |
| ------------------------------------- | --------------------------------------------------------- | ---------------------------------------- |
| issue 或 PR 线程                      | `github:<instance_id>:issue:<owner>/<repo>#<number>`      | `github:7:issue:hx/HX-Email#42`          |
| 仓库 (只作 source 与建 issue 的 sink) | `github:<instance_id>:repo:<owner>/<repo>`                | `github:7:repo:hx/HX-Email`              |
| discussion 线程                       | `github:<instance_id>:discussion:<owner>/<repo>#<number>` | `github:7:discussion:hx/HX-Email#5`      |
| 提交 (push 的提交与提交评论)          | `github:<instance_id>:commit:<owner>/<repo>@<sha>`        | `github:7:commit:hx/HX-Email@0123abc...` |

- issue 与 PR 共用 `#<number>` 编号空间, 同一仓库内不会冲突, 是否是 PR 写在 `raw["gh_thread_kind"]` 这个键里
- 旧前端需要的 `chat_type` 列按规格第 2 节写成 `group`, 路由层不读它
- `instance_id` 对应一个 GitHub App 实例, 一个 App 的多个 installation 共用同一个 `instance_id`, 仓库到 installation 的映射见第 6.5 节

### 3.3 字段映射表

envelope 以规格第 3.1 节为准, 每个字段都有确定的列, 存储增量见规格第 4 节; 下表只列 GitHub 各事件的取值

| envelope 字段       | `issue_comment`                        | `pull_request_review_comment`                 | `pull_request_review` submitted | `issues`                                                              | `pull_request`                                         |
| ------------------- | -------------------------------------- | --------------------------------------------- | ------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------ |
| session             | `...:issue:<full_name>#<issue.number>` | `...:issue:<full_name>#<pull_request.number>` | 同左                            | `...:issue:<full_name>#<issue.number>`                                | `...:issue:<full_name>#<number>`                       |
| sender.id           | `str(comment.user.id)`                 | `str(comment.user.id)`                        | `str(review.user.id)`           | `str(sender.id)`                                                      | `str(sender.id)`                                       |
| sender.name         | `comment.user.login`                   | `comment.user.login`                          | `review.user.login`             | `sender.login`                                                        | `sender.login`                                         |
| text                | `comment.body`                         | `comment.body`                                | `review.state` 加 `review.body` | opened 为标题加空行加正文, 其余为状态句                               | 同左                                                   |
| reply_to            | 空串                                   | `rc:<in_reply_to_id>` 或空串                  | 空串                            | 空串                                                                  | 空串                                                   |
| platform_message_id | `ic:<comment.id>`                      | `rc:<comment.id>`                             | `rv:<review.id>`                | `is:<issue.id>`                                                       | `pr:<pull_request.id>`                                 |
| dedup_key           | 同 platform_message_id                 | 同 platform_message_id                        | 同 platform_message_id          | opened 同 platform_message_id, 其余加 `:<action>:<X-GitHub-Delivery>` | 同左                                                   |
| occurred_at         | `comment.created_at`                   | `comment.created_at`                          | `review.submitted_at`           | `issue.created_at` 或 `issue.updated_at`                              | `pull_request.created_at` 或 `pull_request.updated_at` |

- raw 约定: 至少包含 `gh_event`, `gh_action`, `gh_delivery`, `gh_installation_id`, `gh_repo_id`, `gh_thread_kind`, `html_url`, `sender_type` 这些键
- raw 不存整个 payload, 只存上面这些键与少量事件专有键 (行内评论另含 `path`, `line`), 控制单条消息体积
- `platform_message_id` 带类型前缀, 保证不同对象类型的数字 ID 不会撞车, 也让 edited 事件可以按同一 `dedup_key` 覆盖 text
- 所有时间保留 GitHub 给出的 ISO 8601 UTC 字符串 (以 `Z` 结尾), 不做时区转换
- 状态类消息的 text 用固定模板生成, 例如 "PR #12 closed (merged)", 模板放在 provider 模块内部
- 新增事件的取值: discussion 为 `dn:<discussion.id>`, 标题加正文; discussion_comment 为 `dc:<comment.id>`, `reply_to` 为 `dc:<parent_id>`; commit_comment 为 `cc:<comment.id>`, raw 另含 `path`, `line`; push 的提交为 `cm:<sha>`, `dedup_key` 为 `cm:<full_name>@<sha>`, text 为提交说明, `occurred_at` 由带时区的 `timestamp` 换算成 UTC `Z`
- 每条 envelope 另带触发字段, 随行存入 `trigger_json`, 见 3.5

### 3.4 防回环

- `sender.type == "Bot"` 且 `sender.login == "<app-slug>[bot]"`, 或评论带 `performed_via_github_app` 且其 `id` 等于本 App 时, 该消息以 `sender.is_self=true` 入库, 路由 filter 默认 `exclude_self=true`, 不触发任何自动回复
- 本 App 发出的评论正文末尾带隐藏标记 `<!-- hx-router delivery=<delivery_id> -->`, 入站映射时识别这个标记并从 `text` 中去掉, 作为第二道防线

### 3.5 事件种类与触发判定

| `kind`           | 来源                                                                                         |
| ---------------- | -------------------------------------------------------------------------------------------- |
| `thread_opened`  | issues opened, pull_request opened, discussion created                                       |
| `thread_state`   | issues closed, reopened; pull_request closed, reopened, ready_for_review                     |
| `comment`        | issue_comment, discussion_comment, commit_comment                                            |
| `review_comment` | pull_request_review_comment                                                                  |
| `review`         | pull_request_review submitted; 正文为空的 commented review 不产消息 (它的行内评论各自成消息) |
| `commit`         | push 的每个提交                                                                              |

- `flags.from_self`: 3.4 的防回环判定, 带隐藏标记或由本 App 发出
- `flags.mention_self` 与 `mentions`: 在去掉标记后的正文里找 `@login`, 跳过代码块与行内代码, 跳过邮箱与路径里的 `@`; `@<app-slug>` 与 `@<app-slug>[bot]` 都算提及本 App; 本 App 自己发的消息恒为 false
- `flags.reply_to_self`: 线程 (issue, PR, discussion) 由本 App 开出时, 线程里别人的每条消息都为 true; 带 `reply_to` 的消息 (行内评论回复, discussion 评论回复) 在入库时按 `reply_to` 查同实例的上一条, 它是本 App 发的就为 true
- edited 改写正文时一并改写触发字段, 删掉 `@` 后 `mention_self` 变回 false
- 订阅 filter 的 `kinds` 与 `mention_self` 直接作用在这些字段上; 本次之前入库的 GitHub 行没有存触发字段, 视图里 `mention_self` 与 `reply_to_self` 为 `null`

## 4. 发送侧写入动作清单

路由网关只暴露下表三个写入动作, 通用入口是 MCP 的 `message_send` 与 REST 的 `POST /api/v1/router/messages`; 关闭 issue, 加标签这类非消息动作不在路由网关范围内, 不申请额外权限也不暴露接口

| 动作                      | 触发方式                                                                      | REST 接口                                                                 | 最小权限                                           | 结果未知时                                              |
| ------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------- | ------------------------------------------------------- |
| 发 issue 或 PR 主线程评论 | sink 为 `...:issue:<owner>/<repo>#<number>` 且 `reply_to` 为空或为 `ic:` 前缀 | `POST /repos/{owner}/{repo}/issues/{number}/comments`                     | Issues: write, PR 主线程是否也只需 Issues 写需复核 | 在该线程最近 100 条评论中查标记                         |
| 回复 PR 行内评论          | sink 同上且 `reply_to` 为 `rc:<comment_id>`                                   | `POST /repos/{owner}/{repo}/pulls/{number}/comments/{comment_id}/replies` | Pull requests: write                               | 在该 PR 最近 100 条 review comments 中查标记            |
| 开 issue                  | sink 为 `...:repo:<owner>/<repo>` 且带 `title`                                | `POST /repos/{owner}/{repo}/issues`                                       | Issues: write                                      | 按 `creator=<app-slug>[bot]` 与 `since` 列 issue 查标记 |

### 4.1 delivery_id 标记与结果未知

- GitHub REST 写接口没有平台侧幂等键, 本方案用 outbox 行的 `delivery_id` 模拟: 每次调用都在正文末尾写入 `<!-- hx-router delivery=<delivery_id> -->`
- 调用方的幂等由路由层 outbox 以 `(instance_id, idempotency_key)` 保证, 窗口 7 天, provider 看不到 `idempotency_key`, 只拿到 `OutboundPayload.delivery_id`
- 请求超时或进程在调用中退出时, 路由层把该行置为 `unknown`; GitHub provider 随后按上表查标记, 找到即回填 `platform_message_id` 并置为 `sent`, 确认找不到才重发一次, 查找本身失败则保持 `unknown`, 与规格第 7.3 节一致
- 成功时返回的 `platform_message_id` 带类型前缀 (`ic:`, `rc:`, `is:`), 与入站映射同一套取值

### 4.2 通用重试策略

规则以规格第 7.4 节的重试矩阵为准, 下面是它在 GitHub 上的落点

- 网络错误与 5xx: `SendResult.status="retry"`, 路由层按 2 秒起步翻倍, 单次上限 60 秒, 最多重试 3 次; 每次重发前先查标记
- 超时: `status="unknown"`, 走第 4.1 节的查标记流程
- 401: 视为 installation token 失效, 强制刷新 token 后重试 1 次, 计入上面的 3 次, 仍失败则 `failed` 并把实例状态置为 error
- 403 或 429 且带 `Retry-After`, 或 403 且 `X-RateLimit-Remaining` 为 0: `status="retry"` 并在 `retry_after_seconds` 中给出等待秒数, 这类等待不计入重试次数, 单次等待上限 15 分钟, 自创建起 24 小时仍未发出则 `failed`
- 二级速率限制且没有 `Retry-After`: 至少等待 60 秒, 需复核, 复核方法是查阅 docs.github.com 的 REST 速率限制页面的二级限制说明
- 403 且响应说明触发 abuse 类限制: `failed` 且 `risk_signal=true`, 由路由层按规格第 9.3 节熔断
- 404, 410, 422: `failed`, 常见原因是仓库不在安装范围或 issue 已锁定
- 同一 installation 的写入串行执行, 本地速率为每分钟 30 次写操作, 突发 5 次, 是本项目经验值, 见规格第 9.2 节

## 5. Webhook 接收实现要点

### 5.1 路由与实例定位

- 路由为 `POST /api/v1/router/ingress/github/{instance_id}`, 与 ADR 0005 第 7 节和规格第 6 节一致; `instance_id` 只用于定位实例, 不作为鉴权凭据
- GitHub 无法携带自定义头, 所以 GitHub 实例不使用现有的 `X-Messaging-Token` 鉴权, 改由签名校验完成鉴权
- 路由只做三件事, 读取原始 body 字节, 收集请求头, 调用 provider 的 `verify_event` 与 `parse_event`, 其余逻辑全部在 provider 内部
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

- 投递层去重键为请求头 `X-GitHub-Delivery` 的 GUID, 它在一次投递中全局唯一
- 去重表为规格第 4 节的 `router_ingress_deliveries`, 主键为 `(instance_id, delivery_id)`, 字段含 `event`, `status`, `payload_encrypted`, `received_at`
- 签名通过后先尝试插入该表, 主键冲突说明是重复投递, 直接返回 200 且不再处理
- 手动或通过 API 触发的重投递沿用原 GUID, 因此会被这张表挡住, 这一行为需复核, 复核方法是在 App 设置页对同一投递点击 Redeliver 并比对两次的 `X-GitHub-Delivery`
- GitHub 不会自动重试失败的投递, 失败的投递需要通过 App 的 deliveries 接口主动拉取并重投, 需复核; 本方案只在用户手动触发时补投, 与规格第 7.4 节的入站补投一致
- 第二道去重为消息层的 `(instance_id, dedup_key)` 永久唯一索引, edited 事件覆盖 text
- 去重表保留 7 天, 由路由层 housekeeping 按规格第 10 节分批删除

### 5.4 响应时间

- GitHub 要求在 10 秒内返回响应, 超时即记为投递失败, 需复核
- 本方案目标为 500 毫秒内返回, 同步路径只包含签名校验, 去重插入, 原始 payload 加密落盘三步
- 成功入队返回 202, 重复投递返回 200, 签名错误返回 401, 未订阅事件返回 204
- 异步处理由进程内单个工作线程消费, 负责事件映射, 写入 `messaging_messages`, 更新 installation 缓存
- 进程重启时扫描去重表中 `status = "pending"` 的行重新处理, 保证已返回 2xx 的投递不会丢失

### 5.5 本地开发打通

- 方案一使用 smee: 在 smee.io 新建一个 channel, 把 channel URL 填为 App 的 Webhook URL, 本地运行 `npx smee-client --url <channel> --target http://127.0.0.1:8000/api/v1/router/ingress/github/<instance_id>` 这个地址
- smee 客户端转发时可能重新序列化 JSON, 导致签名校验失败, 需复核, 若遇到此问题改用方案二
- 方案二使用 cloudflared 快速隧道: 运行 `cloudflared tunnel --url http://127.0.0.1:8000`, 把得到的 trycloudflare 地址拼上路由路径填入 App, 原始 body 不被改写
- 本地开发建议单独建一个开发用 App, 只安装到一个测试仓库, 与正式 App 的私钥和 secret 完全隔离
- App 设置页的 Advanced 标签可以查看每次投递的请求与响应, 并手动 Redeliver, 用来回放调试

## 6. Installation token 生命周期管理

### 6.1 签发链路

1. 用 App 私钥签 RS256 JWT, `iat` 取当前时间减 60 秒以抵消时钟偏差, `exp` 取当前时间加 9 分钟, JWT 最长有效期为 10 分钟, 需复核, 复核方法是查阅 docs.github.com 的 App JWT 生成说明
2. JWT 的 `iss` 填 Client ID, GitHub 也接受 App ID, 需复核
3. 用 JWT 调 `POST /app/installations/{installation_id}/access_tokens`, 得到 `token` 与 `expires_at` 两个字段
4. 签发时可在请求体中进一步收窄 `repositories` 与 `permissions`, 写入动作默认收窄到目标仓库

### 6.2 何时刷新

- 每个 token 在内存中记录 `expires_at`, 使用前若剩余有效期少于 5 分钟则先刷新
- 调 API 返回 401 时强制刷新一次, 防止 token 被提前吊销
- 同一 installation 的刷新加单飞锁, 并发请求只触发一次签发, 其余等待结果
- 空闲时不做任何定时刷新, token 过期就让它过期, 下次真正要调 API 时再签, 这是空闲零开销的关键

### 6.3 缓存在哪

- 只有进程内字典 `dict[int, InstallationToken]`, 键为 installation_id, 与规格第 8.1 节一致, token 不落库
- 进程重启后第一次调用 API 时重新签发, 签一次 token 只是一次 HTTP 调用, 不值得为它多一张存放敏感凭据的表

### 6.4 加密存储

- App 私钥 PEM, webhook secret, App ID, Client ID, App slug 一起放进实例配置 JSON, 经 `security.encrypt_secret` 整体加密写入 `messaging_instances.config_encrypted`, 与 QQ 实例完全同一路径
- 任何 API 返回中, 私钥, secret, token 一律脱敏为 `***`, 与现有 event_token 的脱敏规则一致
- 日志中只打印 token 的前 4 位与 `expires_at`, 不打印完整 token 与 JWT
- 去重表中的原始 payload 经 `encrypt_secret` 加密, 因为私有仓库的评论正文属于敏感内容

### 6.5 多 installation 时如何选择

- 一个 HX-Email 实例对应一个 GitHub App, 一个 App 可以有多个 installation, 例如个人账号一个, 组织一个
- 入站事件直接使用 payload 中的 `installation.id`, 回复时沿用该 ID, 不需要查询
- 主动发送时根据 session 地址中的 `<owner>/<repo>` 查映射表 `repo_full_name -> installation_id`, 映射由 `installation` 与 `installation_repositories` 事件维护
- 映射缺失时调 `GET /repos/{owner}/{repo}/installation` (JWT 身份) 查询并写回缓存, 返回 404 说明 App 未安装到该仓库, 直接报错
- installation 被 suspend 或 deleted 时从映射中移除, 并清除对应 token 缓存

## 7. 内存与 CPU

### 7.1 目标值

- 空闲时 CPU 占用目标为 0, 没有轮询线程, 没有心跳, 没有长连接
- 空闲时内存增量目标为不超过 10 MB, 主要是 adapter 对象, installation 映射与少量 token 缓存
- 单个 webhook 的同步路径 CPU 耗时目标为 5 毫秒以内 (不含网络与磁盘), 异步映射目标为 20 毫秒以内
- 以上为本项目设计目标值, 不是外部数字, 落地后用 `ps -o rss` 与压测脚本实测, 偏差超过一倍需要回到本文调整设计; 路由层整体的验收以 ADR 0005 的 A1 到 A4 为准

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
from typing import Literal, Protocol

WriteKind = Literal["comment", "reply_review_comment", "open_issue"]


@dataclass(frozen=True)
class InstallationToken:
    installation_id: int
    token: str
    expires_at: datetime
    repository_ids: tuple[int, ...] = ()
    permissions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GitHubWriteAction:
    kind: WriteKind
    repo_full_name: str
    delivery_id: str
    number: int | None = None
    body: str = ""
    title: str = ""
    reply_to_comment_id: int | None = None


class GitHubProvider(Protocol):
    platform: Literal["github"]

    # MessagingProvider 协议, 签名以 ADR 0005 第 4 节为准
    def list_sessions(self, instance_id: int) -> list[SessionRef]: ...
    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult: ...
    def parse_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> list[dict[str, object]]: ...
    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool: ...

    # GitHub 专有
    def reconcile_unknown(self, session: SessionRef, delivery_id: str) -> SendResult: ...
    def installation_token(self, installation_id: int, *, force_refresh: bool = False) -> InstallationToken: ...


def verify_signature(secrets: tuple[bytes, ...], body: bytes, header_value: str | None) -> bool: ...
```

- `send` 把 `SessionRef` 与 `OutboundPayload` 翻译成 `GitHubWriteAction`, 调用对应 REST 接口, 按第 4.2 节分类成 `SendResult`, 不抛业务异常
- `reconcile_unknown` 实现第 4.1 节的查标记流程, 由路由层对 `unknown` 行调用
- `verify_event` 实现第 5.2 节的签名校验, `parse_event` 实现第 3 节的映射并处理 installation 类事件
- 实例管理与旧前端使用一个继承 `MessagingAdapter` 的 `GitHubAppAdapter`, 它的 `send_message(target, text)` 不直连 GitHub, 而是经 `facade.send` 走同一个 outbox, 由服务端生成 `idempotency_key`

### 8.3 统一接口在 GitHub 上的语义

- `start`: 用 JWT 调 `GET /app` 验证私钥有效, 再调 `GET /app/installations` 预热 installation 映射, 不启动任何线程
- `stop`: 清空内存 token 缓存与映射
- `status`: `state` 为 online 表示 JWT 校验通过且至少有一个 installation, `account_name` 为 `<app-slug>[bot]` 这个登录名
- `create_login`: 返回 `LoginTicket(mode="github_app_install", url="https://github.com/apps/<app-slug>/installations/new")`, 引导用户安装 App
- `check_login`: 至少存在一个未 suspend 的 installation 时 `logged_in=True` 的状态
- `list_sessions` 与 `list_conversations`: 返回本地已入库的线程, 按最近消息时间倒序, 不实时调 GitHub, 避免消耗配额
- `list_groups`: 返回各 installation 可访问的仓库, `group_id` 为 `owner/repo` 这种格式
- `group_action`: 沿用基类默认实现, 抛出 `MessagingError`, API 层按现有约定返回 501

### 8.4 与 QQ provider 必须一致的字段

- 两个 provider 产出的 envelope 字段集合完全相同, 以规格第 3.1 节为准, `sender.id` 与 `platform_message_id` 一律为字符串
- `SendResult` 的 `status` 只取 `sent`, `unknown`, `failed`, `retry`, 与 ADR 0005 第 4 节一致
- 入库统一经路由层 store, 不为 GitHub 另建消息表, 旧 REST 查询接口对前端透明

### 8.5 配置键

- `app_id`, `client_id`, `app_slug`, `private_key_pem`, `webhook_secret`, `webhook_secret_previous` 这六个键, 与规格第 8.1 节一致
- 全部为字符串, 与现有 `MessagingInstance.config: dict[str, str]` 的类型约束一致

## 9. 分阶段落地

阶段与规格第 11 节对应: 本文第一阶段属于规格阶段 1, 第二阶段属于规格阶段 3

### 9.1 第一阶段: 全部事件的监听

- 范围: 第 3.1 节全部事件, installation 生命周期, webhook 路由, 签名校验, 投递去重表, 消息层 dedup_key 去重, installation token 管理
- 权限: Metadata 只读, Issues 读写, Pull requests 读写
- 验收: 在测试仓库发一条 issue 评论, 5 秒内能用 `messages_pull` 读到对应 envelope
- 验收: 在 App 设置页对同一投递点击 Redeliver, 消息表中不出现重复记录
- 验收: 用错误 secret 签名的请求返回 401 且不入库

### 9.2 第二阶段: 发送

- 范围: 第 4 节的三个写入动作, delivery_id 标记与结果未知查重, 第 4.2 节的重试与限流落点
- 验收: 通过 MCP 对 issue 发评论并在 GitHub 上看到由 App 身份发出, 且不触发回环
- 验收: 模拟评论请求超时且评论实际已创建时, 该行经查标记回填为 `sent`, GitHub 上只有一条评论
- 验收: 支持 webhook secret 轮换, 轮换期间新旧 secret 签名的请求都通过

## 10. 风险与需复核事项汇总

- 第 1.4 节全部速率数字需复核, 复核方法是查阅 docs.github.com 的 Rate limits for the REST API 页面并记录查阅日期
- PR 主线程评论所需权限是 Issues 写还是 Pull requests 写即可, 需复核
- 重投递是否沿用原 `X-GitHub-Delivery` GUID, 需复核
- GitHub 是否会自动重试失败投递, 需复核
- 10 秒响应时限与 JWT 10 分钟有效期, 需复核
- `X-GitHub-Hook-Installation-Target-ID` 请求头名称, 需复核
- smee 客户端是否改写 body 导致签名失败, 需复核
- 评论正文长度上限 (约 65536 字符), 需复核; 路由层入参上限为 4000 字符, 远低于该值, 因此 provider 不需要截断
