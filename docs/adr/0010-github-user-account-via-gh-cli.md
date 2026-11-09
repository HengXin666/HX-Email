# 0010 GitHub 用户账号经 gh CLI 接入, 作为独立平台 github_user, 与 GitHub App 并存

## Status

Accepted (2026-11-09). 不取代任何既有决策; GitHub App (`github`, docs/providers/github-app.md) 保持不变.

## Context

GitHub App 以 `<slug>[bot]` 身份行动, 靠仓库级 webhook 收事件. 有两类需求它做不到:

- 以真人或专用账号身份出现在 issue, PR, review 与 discussion 里 (例如被请求 review 的是一个用户, 不是 App).
- 读这个账号自己的 notifications: 谁 @ 了它, 谁请求它 review, 谁把 issue 指派给它. App 没有 notifications.

参考 deepseek-ai/dsh-superagent-prototype 的做法: agent 以一个专用 GitHub 用户账号行动, 每个账号一个 gh 包装脚本
(`GH_CONFIG_DIR=... exec gh "$@"`), 用户在终端里自己 `auth login`; 系统只配置 CLI 的绝对路径.

## Decision

- 新增独立平台 `github_user`, 而不是 `github` 平台下的一种 auth 模式. 理由: 实例类型必须与地址平台一致, 两者是两个身份, 两种入站方式 (push 与 pull), 两套凭据与限额桶; 放进同一平台会让 App 实例的配置解密, 整形桶与入站路径都要分叉, 改动 App 行为的风险大于多一个平台名. 地址树, 事件种类与动作参数直接复用 `github` 的声明, 消费者看到的 envelope 与 App 同形, 只有平台前缀不同.
- 用 gh CLI 而不是存 OAuth token: token 留在用户自己的 `GH_CONFIG_DIR` 里, 由 gh 负责登录, 刷新与存储; 本服务只保存一个可执行文件路径, 数据库泄露也不泄露凭据; 换号或吊销在终端完成, 不经过网页. 代价是每次请求起一个子进程, 对每分钟一次的轮询与人工节奏的写入可以接受.
- 凭据边界: 子进程环境清掉 `GH_TOKEN`, `GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN`, `GITHUB_ENTERPRISE_TOKEN`, `GH_HOST`, `GH_CONFIG_DIR` 以及名字含 `KEY`, `PASSWORD`, `SECRET`, `TOKEN` 的全部变量, 只用包装脚本自己的凭据; 网页上没有任何 token 输入; 只支持 github.com; CLI 路径只能由管理员配置 (它是服务端要执行的程序); 一个实例只读写配置的那一个仓库, 只标已读本仓库里本服务处理过的通知.
- 与 App 的分工: App 是仓库级 webhook, 以 bot 身份行动; 用户账号以真人或专用账号身份行动, 轮询 notifications (遵守 `X-Poll-Interval`, `If-Modified-Since`), 可选按开关增量拉仓库动态. 出站动作集与 App 相同, 全部经 `<cli> api` (REST 与 GraphQL), 复用 App 的请求构造, 隐藏标记, 幂等, unknown 与重试分类; 权限声明写成 OAuth scope.
- 这条线是为后续设计 dsh-superagent 式 agent 做准备: agent 以专用账号身份被 @, 被请求 review, 被指派, 再以同一身份回帖与提交 review, 消息经路由层订阅与 `action_invoke` 进出.

## Consequences

- 部署机器上要装 gh 并为每个账号建包装脚本; 服务以运行用户的身份执行它.
- 编辑正文新加的 `@` 收不到通知; 进程重启后 observe 游标不回补停机期间的动作.
- 没有用真实 gh 账号联调, 复核项见 docs/providers/github-user.md 7.
- v1 地址的平台段校验放宽为 `[a-z0-9_]+`, 与能力声明的平台名规则一致.

## Links

- provider 规格: [`docs/providers/github-user.md`](../providers/github-user.md)
- App 规格: [`docs/providers/github-app.md`](../providers/github-app.md)
- 决策记录: `.agents/notes/implemented/feature/2026-11-09-github-cli-account.md`
