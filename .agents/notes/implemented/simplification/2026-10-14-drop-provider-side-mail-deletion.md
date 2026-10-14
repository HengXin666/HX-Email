# Agent Note: 邮件永久删除功能整体移除

Status: implemented

## Problem

前端邮件列表每封邮件右侧的删除按钮, 以及 `POST /api/v1/emails/delete`、
`POST /api/v1/usable-emails/{id}/messages/delete` 两个接口, 会在 Gmail/Outlook 上游永久删除邮件。
Gmail 账号默认 `expungeBehavior=archive` 时, 服务端对 `STORE +FLAGS (\Deleted)` 与 `EXPUNGE`
回 OK 却把标记丢掉 (实测: 下一次 FETCH 标记已不在、UID 仍在列表里), 功能只能报
`gmail_flag_ignored` 并让用户去改 Gmail 设置 —— 对本实例的 Gmail 池基本不可用, 用户判定无用。

## Decision

整条链路删除, 不留兼容层: `server/mail/deletion/` 整个包 (targets / purge / imap_prune /
graph_prune / gmail_settings / report)、`graph/graph_delete.py`、`impl/message/delete_service.py`、
两个 API 接口与 `DeleteEmailRequest`、`GraphMailProvider.delete_message`、
`FallbackMailProvider.delete_message`、`fetched_messages.purge_uid` 列与它的 backfill、
以及 web 侧的删除按钮、`deleteMessages` 客户端与 `DeleteMessagesResult` 类型。

保留: `fetched_messages.message_id` (IMAP UID) —— 增量拉取的 UID 窗口仍要用它,
`backfill_message_uid` 只补这一列; `delete_messages_for_email` (删可用邮箱时清本地行) 与
删账号/删分组等其它删除功能与本次无关。

地址→账号的 `resolve_account_for_address` 原在 `impl/message/` (该包因本次删除只剩它一个文件),
挪到 `impl/accounts/account_service.py`, 由 `impl.accounts` 包导出, `impl/email_service.py` 继续
转出给外部 API 使用。

## Alternatives considered

- **保留接口, 只在 Gmail 失败时给提示** — 改动最小, 而且 `gmail_flag_ignored` 的提示与
  `settings_url` 深链都已经写好。否决: 用户判定该功能无用; 留着就是一条在本实例永远不生效的
  写路径, 外加一套测试、一列 schema、一份接口文档。
- **只摘前端按钮, 后端与外部 API 保留** — 前端看不见就不会误用。否决: 外部 API 与
  `docs/` 仍暴露永久删除, 行为依旧不可靠, 且留下没有调用者的死代码。
- **什么都不做 / 复用现有** — 「复用现有」在这里等于保留一条删不掉的删除路径; 不做的代价是
  用户继续被一个删不掉的按钮和一条失败提示困扰。

## Consequences

少了一个横跨 imap / graph / api / web / docs 的子系统, 每封邮件的删除不再需要一次
IMAP 或 Graph 会话, `fetched_messages` 少一列。代价: 用户不能在上游邮箱永久删除单封邮件了
(本地列表仍随账号/可用邮箱的删除而清理); 老库里已存在的 `purge_uid` 列会留下但不被读写
—— `models/schema_migrations.py` 只有加列迁移, 没有减列迁移。

## Testing

覆盖该功能的 `server/tests/test_message_deletion.py`、`test_imap_prune.py`、`test_graph_delete.py`
随代码删除, `test_email_idor.py` 去掉 `/emails/delete` 的断言, web 侧 `emails.delete.test.ts` 删除。
门禁是 `bash scripts/verify.sh` (ruff / mypy / arch / biome / tsc / knip / pytest / vitest / playwright)。
