# Agent Note: github_user 真实联调后的修正 (失败原因透出, 同名 discussion 匹配, discussion scope, 空列表 Last-Modified)

Status: implemented

Decision-ID: github-user-live-fixes

## Code

- `server/src/hx_email/server/router/providers/impl/github/github_http.py`
- `server/src/hx_email/server/router/providers/impl/github_user/gh_inbox.py`
- `server/src/hx_email/server/contract/github_user/actions.py`

## Problem

用真实 gh (2.102.0, 经典 token, 只有 `repo` 没有 `write:discussion`) 在私有测试仓库上跑完 github_user 的读写路径
(docs/providers/github-user.md 7), 发现四处与实现假设不符:

1. 终态失败只报状态码. 对自己的 PR `APPROVE` 时 GitHub 回 422 `errors: ["Review Can not approve your own pull request"]`,
   调用方只看到 `GitHub rejected the payload as unprocessable`, 不知道该改什么. 403, 404 同理.
2. Discussion 通知按标题取 "最近更新的第一个": 一个后建的同名 discussion 会抢走旧 discussion 里的回复通知;
   查询只取顶层 `comments(last: 1)`, 楼中楼回复永远不会被当作最新评论. 原查询还批量拉 20 个 discussion 的正文.
3. 动作声明里 discussion 需要 `write:discussion`. 实测只有 `repo` 时 `createDiscussion` 与 `addDiscussionComment` 都成功;
   GitHub 文档写明仓库 discussion 的 GraphQL 只要 `repo` (公开仓库 `public_repo`), `write:discussion` 管的是团队 discussion.
4. 未读列表为空的 200 不带 `Last-Modified`, 代码把它当作新值写回空串, 之后每轮都是不带 `If-Modified-Since` 的计费请求.

## Decision

- `classify_response` 的 401, 403, 404, 422 终态把 GitHub 的 `message` 与 `errors[]` (字符串或 `{message|code}`) 拼成一行附在错误后面,
  截断到 300 字符, 不保存整个响应. 错误码与重试分类不变, App 与 github_user 共用.
- Discussion 匹配分两步: 第一步只取 20 个 discussion 的编号, 标题, 创建时间与最近 3 条评论及其最新回复的时间 (不带正文);
  同标题有多个时取最近一次动态离通知 `updated_at` 最近的; 第二步按编号取那一个的正文与评论, 评论与回复里 `createdAt`
  最新的作为消息. 只有一个同名时行为与原来相同.
- `DISCUSSION_SCOPES` 改为与其它动作相同的 `("repo",)`; setup 检查的缺失判断本来就只看 `repo`, 不变.
- 200 没有 `Last-Modified` 时保留上一轮的值.

## Alternatives considered

- 什么都不做 / 复用现有: 最强理由是这四处都不影响写入成功与入库去重, 改动越少越不会碰坏 App. 否决: 第 1 条让调用方无法自行纠错
  (agent 会盲目重试或放弃), 第 2 条会把消息挂到错误的 discussion 会话上, 第 3 条让前端与 `capabilities_list` 要求用户多授权一个
  不相关的 scope.
- 透出完整响应体: 最强理由是信息最全. 否决: 响应体可能很大且含无关字段, 错误信息会进数据库 (outbox 的 last_error);
  `message` 加 `errors[]` 已经足够定位, 并截断上限.
- Discussion 通知改用 GraphQL `notifications` 或 `search` 定位: 最强理由是可能拿到精确编号. 否决: 公开 API 的通知没有 GraphQL 入口,
  按标题 search 一样不精确且多一次计费请求; 用时间就近已能区分实测中的混淆情形, 两次请求都很小.
- 只在同标题时多查一次正文 (保持一步查询): 最强理由是少一次请求. 否决: 一步查询要带 20 份正文与评论正文, stdout 可能逼近 4 MiB 上限;
  分两步后每次响应都很小, 多出来的一次 GraphQL 只在确有 discussion 通知时发生.
- `Last-Modified` 缺失时改用 `ETag` / `If-None-Match`: 最强理由是空列表也能 304. 否决: 多一个状态字段与分支; 保留旧值已经覆盖
  "处理完再次为空" 的常见情形, 仓库从未有过通知时多花的是每分钟一次请求, 在 5000/小时的额度里可以接受.

## Consequences

- 回归测试在 `server/tests/test_router_github_user_live.py`, 输入取自真实 gh 输出, 不依赖真实账号.

- 同名且动态时间几乎相同的 discussion 仍可能选错 (两者相差不到通知粒度); 由别的账号触发的真实 discussion 通知还没验证过,
  见 docs/providers/github-user.md 7 的未验证项.
- 只看最近 3 条顶层评论及各自最新一条回复; 更早楼层里的新回复看不到, 会退而取这几条里最新的一条.
- App 的错误信息变长 (带原因), 依赖精确错误文本的调用方需要改用 `error_code`.
- 联调步骤与清理清单写在 docs/providers/github-user.md 8, 测试仓库用占位符.
