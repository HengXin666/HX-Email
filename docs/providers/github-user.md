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
- 经典 token 需要 `repo` scope (含 notifications 与仓库 discussion 读写; 公开仓库可以只给 `public_repo`, 但 setup 检查按 `repo` 报缺失). `write:discussion` 管的是团队 discussion, 不需要 (第 7 节实测).
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
- Discussion 通知不带编号: 先只取最近更新的 20 个 discussion 的标题与时间 (不带正文), 同标题有多个时取最近一次动态 (正文, 评论, 楼中楼回复) 离通知 `updated_at` 最近的那个, 再按编号取它的正文与最近 3 条评论及各自最新回复, 其中最新的一条 (可能是回复) 作为消息.
- observe 开关: `GET /issues?state=all&since=` (含 PR), `GET /issues/comments?since=`, `GET /pulls/comments?since=`, `GET /actions/runs?status=completed` 第一页; 逐页处理, 游标是本轮见到的最大 `updated_at`. CI 结果落在 `commit` 会话, 事件种类 `ci`, 消息 id `ci:<run id>`.
- 编辑 issue 或评论正文时新加的 `@` GitHub 不发通知, 这里收不到; 需要时打开 `observe_comments`.
- 本账号自己的动作 GitHub 不产生通知: 自己发的评论与 issue 只能经 observe 开关回流 (标 `from_self`). observe 不覆盖 review 本身 (只有 review 评论), discussion 与表情, 所以这些出站动作没有回流消息.

## 4. 出站

`message_send` (发到 issue 线程即评论, 发到仓库即新开 issue) 与 `comment_create`, `reaction_add`, `review_submit`, `discussion_create`, `discussion_comment_create`,
全部走 `<cli> api` (REST 与 `graphql`), 复用 App 的请求构造与结果分类:

- 隐藏标记 `<!-- hx-router delivery=... -->` 与 App 相同
- 超时或 CLI 非零退出且没有 HTTP 状态行: 写入进 `unknown`, 不自动重发; 表情与查询超时可重试
- 403 限流, 429, 5xx 重试; 401, 403, 404, 422 终态, 错误信息带 GitHub 的 `message` 与 `errors[]` (截断 300 字符), 例如对自己的 PR `APPROVE` 得到 `unprocessable: GitHub rejected the payload as unprocessable: Unprocessable Entity; Review Can not approve your own pull request`
- 对配置之外仓库的写一律 `not_found`, 不调用 CLI; 未通过检查的实例返回 `provider_offline` 重试
- 按实例 `disabled_actions` 拒绝关掉的动作 (`action_not_supported`)

| 动作                                                              | 声明的 scope |
| ----------------------------------------------------------------- | ------------ |
| `message_send`, `comment_create`, `reaction_add`, `review_submit` | `repo`       |
| `discussion_create`, `discussion_comment_create`                  | `repo`       |

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

## 7. 真实联调结论 (gh 2.102.0, 经典 token, scope `gist, read:org, repo, workflow`)

在一个私有测试仓库上跑过全部读写路径, 写出来的东西已删除. 结论:

| 项                                                | 结论                                                                                                                                                                                       |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--include` 的 304                                | 退出码 1, stdout 是状态行 `HTTP/2.0 304 Not Modified` + 响应头 + 空行, 没有 body, stderr 为 `gh: HTTP 304`; 解析按状态行得到 304, 通过. 304 不计入 `X-Ratelimit-Used`                      |
| `--include` 的 205                                | 标已读 `PATCH /notifications/threads/{id}` 退出码 0, 状态行 `HTTP/2.0 205 Reset Content`, 空 body; 计为已标, 通过                                                                          |
| 输出格式                                          | 状态行以 `\n` 结尾, 其余头行以 `\r\n` 结尾, 头与 body 之间 `\r\n\r\n`; 4xx 退出码 1 但 stdout 仍是完整响应, 按状态码分类                                                                   |
| 空未读列表                                        | 200 `[]` 不带 `Last-Modified` (只有 `Etag`). 已修: 这时保留上一轮的 `Last-Modified`, 下一轮仍可拿到免费的 304                                                                              |
| 轮询入库                                          | 实例上线后一轮收到并入库该仓库全部未读通知 (reason `author`), 处理完的线程全部标已读; 第二轮 304                                                                                           |
| observe 游标                                      | 开关打开后首轮以当时时刻为游标; 之后新建 issue, 评论, review 评论, PR 关闭都在下一轮回流; 游标推进到本轮最大 `updated_at`, 边界上的条目重复出现但不重复入库                                |
| scope 检查                                        | 这个 token 返回 `missing_scopes: []`, 正确: 通知与仓库 discussion 都只要 `repo`                                                                                                            |
| `message_send` 到仓库                             | 新开 issue, 带隐藏标记, 返回 `is:<id>`                                                                                                                                                     |
| `comment_create`                                  | issue 与 PR 线程评论, 以及 `reply_to=rc:<id>` 回复 review 评论, 均成功; 同一幂等键重放返回 `deduplicated: true` 且不再调用 CLI                                                             |
| `reaction_add`                                    | 线程本身与 `ic:`, `rc:` 评论上均成功, 返回 `re:<id>`                                                                                                                                       |
| `review_submit`                                   | `COMMENT` 成功 (`rv:<id>`). 对自己的 PR `APPROVE` 与 `REQUEST_CHANGES` 被 GitHub 422 拒绝, 原来只报 "unprocessable", 已修为带上 GitHub 的原因. 目标是普通 issue 时在本地拒绝, 不调用写接口 |
| `discussion_create` / `discussion_comment_create` | 只有 `repo`, 没有 `write:discussion` 时成功, 含 `reply_to=dc:<id>` 楼中楼; category 按名称或 slug 匹配, 不存在时本地报 `invalid_payload`. 声明的 scope 已改为只有 `repo`                   |
| Discussion 按标题匹配                             | 实测有误: 同名的新 discussion 会把旧 discussion 里一条回复的通知抢走, 且楼中楼回复不被当作最新评论. 已修 (见第 3 节)                                                                       |
| 只写配置的仓库                                    | 对别的仓库写返回 `not_found`, 错误里带原因, 不调用 CLI                                                                                                                                     |

仍未验证:

- 由别的账号触发的通知 (`mention`, `review_requested`, `assign`, `team_mention`, discussion 通知): 测试只用了一个账号, 自己的动作不产生通知. discussion 通知的 `subject` 是否真的没有编号, 以及按时间挑选在真实通知上的准确度, 需要第二个账号.
- fine-grained token: 不返回 `X-OAuth-Scopes`, scope 缺失检查此时不生效; 没有实测.
- 公开仓库只给 `public_repo` 的情况: setup 检查会报缺 `repo`, 实际可用, 没有实测.
- 超过一页 (50 条) 的通知分页与 `X-Poll-Interval` 大于 60 的情况没有遇到.

## 8. 联调手册 (写操作会公开发帖, 只在自己的测试仓库上跑)

占位符: `<cli>` 是包装脚本, `<owner>/<repo>` 是测试仓库, `<iid>` 是实例 id, 地址前缀 `github_user:<iid>/repo/<owner>/<repo>`.

1. 本地起服务 (临时数据目录), 管理员登录后 `POST /api/v1/router/github_user/save {"cli": "<cli>", "repository": "<owner>/<repo>"}`, 确认 `report.ok` 与 `missing_scopes`; `PUT /api/v1/messaging/instances/<iid>/config` 打开四个 `observe_*` 开关, 自己的动作才会回流.
2. 打开 discussions (结束时恢复): `gh api -X PATCH repos/<owner>/<repo> -F has_discussions=true`. 注意要用 `-F`; `-f has_discussions=false` 传的是字符串, 关不掉.
3. 用 MCP `action_invoke` (或 `POST /api/v1/router/actions`) 依次: `message_send` 到仓库 (带 `title`) 新开 issue; 对 `.../issue/<n>` 跑 `comment_create`, `reaction_add` (线程与 `message_id=ic:<id>`); 等一轮轮询, 用 `messages_pull` 确认 `is:` 与 `ic:` 回流.
4. review: `git/refs` 建临时分支, `contents` 提交一个测试文件, 开 PR; `review_submit event=COMMENT body=...`; 再试 `APPROVE` 看错误信息; 可用 `gh api -X POST repos/<owner>/<repo>/pulls/<n>/comments` 建一条行内评论, 再测 `comment_create reply_to=rc:<id>` 与 `reaction_add message_id=rc:<id>`.
5. discussion: `discussion_create category=General`, 对 `.../discussion/<n>` 跑 `discussion_comment_create` 与 `reply_to=dc:<id>`.
6. 清理 (全部用 `gh api`): 先删表情 (`DELETE .../reactions/<id>`), 再删评论 (`issues/comments/<id>`, `pulls/comments/<id>`, 包括机器人在临时 PR 上的评论), GraphQL `deleteDiscussion` 删 discussion, issue 先关再 `deleteIssue`, PR 关闭并删分支 (`DELETE git/refs/heads/<branch>`), 最后 `-F has_discussions=false`. 已提交的 review 与 PR 本身 GitHub 不允许删除, review 评论删掉后只剩 review 正文.
7. 列一遍 issues, pulls, branches 与 GraphQL `discussions { totalCount }` 核对没有残留. 注意轮询会把该仓库的未读通知标为已读.
