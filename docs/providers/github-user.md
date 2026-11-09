# GitHub 用户账号 (gh CLI) 接入: `github_user`

决策: [ADR 0010](../adr/0010-github-user-account-via-gh-cli.md). 与 [GitHub App](github-app.md) 并存, 互不影响.

## 1. 准备 gh 包装脚本 (每个账号一个)

本服务从不保存这个账号的 token. 在运行本服务的机器上, 为专用账号建一个包装脚本, 让它用独立的
`GH_CONFIG_DIR`:

```sh
mkdir -p ~/.local/bin ~/.config/gh-agent
cat > ~/.local/bin/gh-agent <<'SH'
#!/bin/sh
GH_CONFIG_DIR="$HOME/.config/gh-agent" exec gh "$@"
SH
chmod +x ~/.local/bin/gh-agent
~/.local/bin/gh-agent auth login        # 在终端里交互登录, 选 github.com
~/.local/bin/gh-agent api user --jq .login   # 能打印登录名就说明可用
```

- 只支持 github.com, 不支持 GitHub Enterprise (所有调用都带 `--hostname github.com`).
- 经典 token 需要 `repo` scope (含 notifications); discussion 写入另列 `write:discussion` (需复核, 见第 7 节).
- 网页上只填 CLI 的绝对路径 (例如 `/home/you/.local/bin/gh-agent`) 和仓库 `owner/name`, 不填任何 token.

## 2. 子进程边界

- 每次调用都是 `<cli> api --hostname github.com --include --method <M> <endpoint> [--input -]`, 用 asyncio subprocess 启动.
- 启动前清理环境: 去掉 `GH_TOKEN`, `GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN`, `GITHUB_ENTERPRISE_TOKEN`, `GH_HOST`, `GH_CONFIG_DIR`,
  以及名字里含 `KEY`, `PASSWORD`, `SECRET`, `TOKEN` 的全部变量; 再设 `GH_PROMPT_DISABLED=1`, `GH_NO_UPDATE_NOTIFIER=1`, `NO_COLOR=1`.
  于是子进程只能用包装脚本自己 `GH_CONFIG_DIR` 里的凭据.
- 超时 90 秒, 超时后杀掉子进程, 错误信息写明是哪个程序 (`<cli> did not finish within 90s`).
- stdout 分块读取, 超过 4 MiB 杀进程; stderr 只留 16 KiB.

## 3. 实例配置与入站

接入只能由管理员在 Messaging 页面的「GitHub 账号 (gh CLI)」卡片完成 (对应 `POST /api/v1/router/github_user/save` 与 `/check`); 通用建实例接口不接受 `github_user`, 因为 CLI 路径是服务端要执行的程序.

| 键                                                                     | 说明                                                                            |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `cli`                                                                  | 包装脚本绝对路径                                                                |
| `repository`                                                           | `owner/name`, 一个实例只服务一个仓库, 入站与出站都限定在它上面                  |
| `observe_issues` / `observe_pulls` / `observe_comments` / `observe_ci` | `1` 开, 默认全关                                                                |
| `poll_seconds`                                                         | 轮询间隔, 默认 60, 不低于 60                                                    |
| `login`                                                                | 检查通过后服务端写入的登录名, 用于 `from_self`, `mention_self`, `reply_to_self` |
| `disabled_actions`                                                     | 与 App 相同的出站动作开关                                                       |

setup 检查依次报告: `cli_not_configured`, `cli_not_absolute`, `cli_not_found`, `cli_not_executable`, `repository_invalid`,
`not_authenticated` (提示 `<cli> auth login`), `cli_timeout`, `cli_failed`, `repo_not_visible`, `repo_no_read`, `repo_no_push`; 通过时返回登录名,
经典 token 还返回 scope 列表与缺少的 scope. 通过才置实例 `online`, 轮询与出站只认 `online` 实例.

入站 (守护线程里的 asyncio 循环, `server/gateway/impl/github_user_poll.py`):

- notifications: 只请求 `GET /repos/{owner}/{name}/notifications`, 第一页带 `If-Modified-Since`, 304 即无事; 下一轮不早于 `X-Poll-Interval`.
  逐页处理 (50 条一页, 最多 10 页), 全部页处理完才统一 `PATCH /notifications/threads/{id}` 标已读; 任一线程取详情失败时不推进 `Last-Modified`, 下一轮重来, 靠去重键不重复入库.
- 开关全关时只处理 reason 为 `mention`, `team_mention`, `review_requested`, `assign`, `author` 的线程; 其余线程保持未读, 不替用户标已读.
- 归一: 拉到的 issue, 评论, discussion 拼成 App webhook 的载荷形状, 交给 App 的映射表, 得到与 App 相同的 envelope (同样的 `kind`, 消息 id 前缀 `ic:`, `rc:`, `dc:`, `is:`, `pr:`, `dn:`), 只把平台前缀换成 `github_user`, 并按登录名重判三个自我信号.
  被指派, 被请求 review 这类没有新评论的通知, 落成线程的 `thread_opened` 消息, 去重键带 reason 与通知时间, 每次通知一条.
- Discussion 通知不带编号: 按标题在最近更新的 20 个 discussion 里匹配, 取最新一条评论.
- observe 开关: `GET /issues?state=all&since=` (含 PR), `GET /issues/comments?since=`, `GET /pulls/comments?since=`, `GET /actions/runs?status=completed` 第一页; 逐页处理, 游标是本轮见到的最大 `updated_at`. CI 结果落在 `commit` 会话, 事件种类 `ci`, 消息 id `ci:<run id>`.
- 编辑 issue 或评论正文时新加的 `@` GitHub 不发通知, 这里收不到; 需要时打开 `observe_comments`.

## 4. 出站

`message_send` (发到 issue 线程即评论, 发到仓库即新开 issue) 与 `comment_create`, `reaction_add`, `review_submit`, `discussion_create`, `discussion_comment_create`,
全部走 `<cli> api` (REST 与 `graphql`), 复用 App 的请求构造与结果分类:

- 隐藏标记 `<!-- hx-router delivery=... -->` 与 App 相同
- 超时或 CLI 非零退出且没有 HTTP 状态行: 写入进 `unknown`, 不自动重发; 表情与查询超时可重试
- 403 限流, 429, 5xx 重试; 401, 403, 404, 422 终态
- 对配置之外仓库的写一律 `not_found`, 不调用 CLI; 未通过检查的实例返回 `provider_offline` 重试
- 按实例 `disabled_actions` 拒绝关掉的动作 (`action_not_supported`)

| 动作                                                              | 声明的 scope               |
| ----------------------------------------------------------------- | -------------------------- |
| `message_send`, `comment_create`, `reaction_add`, `review_submit` | `repo`                     |
| `discussion_create`, `discussion_comment_create`                  | `repo`, `write:discussion` |

## 5. 与 GitHub App 的分工

|      | GitHub App (`github`) | 用户账号 (`github_user`)                         |
| ---- | --------------------- | ------------------------------------------------ |
| 身份 | `<slug>[bot]`         | 真人或专用账号                                   |
| 入站 | 仓库级 webhook 推送   | 轮询该账号的 notifications                       |
| 凭据 | App 私钥加密存库      | token 只在包装脚本的 `GH_CONFIG_DIR`, 服务不持有 |
| 范围 | 安装了 App 的仓库     | 配置的那一个仓库                                 |

两条线互不改动: App 的代码路径, 配置与测试未变.

## 6. 内存

不缓存任何响应; 每个实例只在内存里留下次到期时间, `Last-Modified` 与 observe 游标三个小字段. 列表一律分页, 一次只持有一页; 进程重启后 observe 游标从重启时刻开始, 停机期间的仓库动态不回补 (notifications 未读的仍会收到).

## 7. 需复核 (没有用真实 gh 账号联调)

- `gh api --include` 在 304 与 205 上的退出码与输出格式, 以真实 gh 版本为准 (解析只依赖状态行).
- 经典 token 写仓库 discussion 是否只需 `repo`; `write:discussion` 是否多余.
- Discussion 按标题匹配在同名 discussion 时可能取错.
- fine-grained token 不返回 `X-OAuth-Scopes`, scope 缺失检查此时不生效.
