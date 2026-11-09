# Agent Note: GitHub 用户账号经 gh CLI 接入, 独立平台 github_user 与 App 并存

Status: implemented

Decision-ID: github-cli-account

## Code

- `server/src/hx_email/server/router/providers/github_user.py`
- `server/src/hx_email/server/router/providers/impl/github_user/gh_cli.py`
- `server/src/hx_email/server/contract/github_user/config.py`
- `server/src/hx_email/server/gateway/impl/github_user_poll.py`
- `server/src/hx_email/api/impl/router/github_user_routes.py`
- `web/src/pages/impl/GithubUserConnect.tsx`
- `web/src/pages/Messaging.tsx`
- `web/src/types/messaging.ts`

## Problem

GitHub App 以 `<slug>[bot]` 身份行动, 只靠仓库级 webhook 收事件, 读不到任何账号的 notifications. 需要一个以真人或专用账号身份行动, 能被 @, 被请求 review, 被指派并以同一身份回帖的入口, 为后续 dsh-superagent 式 agent 做准备; 同时 App 那条线不能有任何行为变化.

## Decision

- 独立平台 `github_user` (ADR 0010): 地址树, 事件种类与动作参数复用 `github` 的声明, 投递方式 `pull`, 多一个事件种类 `ci`; 动作 `requires` 写成 OAuth scope.
- 凭据: 只保存 gh 包装脚本的绝对路径; 子进程用 asyncio subprocess 启动, 清掉 `GH_TOKEN` 等与名字含 KEY, PASSWORD, SECRET, TOKEN 的变量, 超时 90 秒并在错误里写明程序路径; stdout 分块读, 超 4 MiB 杀进程. 网页上没有 token 输入, 接入端点仅管理员可用, 通用建实例接口拒绝该平台.
- 出站: provider 实现 App 写代码要的 `GitHubCaller` 形状 (`call`, `send`, `post`, `clock`), 网络出口换成 `<cli> api`, 地址前缀换回 `github` 后直接复用 `build_write_action`, `action_request`, `invoke_github` 与 GraphQL 分类; 只写配置的那一个仓库, 未通过检查的实例不调用 CLI.
- 入站: 守护线程里的 asyncio 循环轮询本仓库 notifications (If-Modified-Since, X-Poll-Interval, 分页, 全部页处理完才统一标已读, 出错不推进 Last-Modified); 开关全关只收与本账号有关的 reason; observe 开关按 since 增量分页拉. 归一把数据拼成 App webhook 载荷交给 App 的 `MAPPERS`, 只换平台前缀并按登录名重判自我信号.
- v1 地址平台段放宽为 `[a-z0-9_]+`, 与能力声明的平台名规则一致.

## Alternatives considered

- 什么都不做 / 复用现有 App: 最强理由是零新代码, App 已有全部写动作. 否决: App 没有 notifications, 也不能以用户身份被请求 review 或被指派.
- 放进 `github` 平台作为一种 auth 模式: 最强理由是消费者少认一个平台名, 地址前缀统一. 否决: 实例类型与地址平台必须一致, 两种身份的配置 (加密 App 凭据 vs 明文 CLI 路径), 入站 (push vs pull) 与限额桶都要在 App 代码里分叉, 改动 App 行为的风险更大.
- 存 OAuth token (设备流或网页填 PAT): 最强理由是不依赖本机装 gh, 每次请求不起子进程. 否决: token 会进数据库与网页, 刷新与吊销要自己做; gh 已经做好登录与存储, 包装脚本让凭据边界清楚.
- 同步 `subprocess.run`: 最强理由是 provider 协议是同步的, 写法更短. 否决: 轮询要在一个循环里并发管理多个账号的子进程与超时, asyncio 子进程可以流式读输出并在超时时干净地杀进程; 同步的出站调用用 `asyncio.run` 包一层即可.
- 边翻页边标已读: 最强理由是不用记住 thread id. 否决: 标已读会让未读列表前移, 下一页会漏掉条目; 只留 id 列表 (最多 500 个) 内存可忽略.

## Consequences

- 部署机器上要有 gh 与包装脚本; CLI 由服务进程的用户执行, 所以只有管理员能配置路径.
- 编辑正文新加的 `@` 收不到; 重启后 observe 游标不回补停机期间的动态.
- 已用真实 gh 账号联调, 结论与仍未验证的项见 docs/providers/github-user.md 7; 联调后的修正见 `.agents/notes/implemented/feature/2026-11-09-github-user-live-fixes.md`.
- `reconcile_unknown` 与 App 一样暂无调用方, 用户账号 provider 也没有实现它.
