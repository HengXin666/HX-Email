# Agent Note: 逻辑文件夹名由服务器 LIST 的特殊属性解析, 而不是猜英文名

Status: implemented

## Problem

Gmail 的 `[Gmail]/...` 系统文件夹名随账号语言变化, 且用 modified UTF-7 返回: 实测同一个
`imap.gmail.com` 上, 英文账号的垃圾箱是 `[Gmail]/Spam`, 中文账号的是 `[Gmail]/&V4NXPpCuTvY-`。
收信路径的 `REFRESH_FOLDERS` 要读逻辑名 `junk`, 而 `imap/impl/folder_candidates.py` 只列英文名,
于是 `SELECT '[Gmail]/Spam'` 与 `SELECT 'junk'` 都被拒绝, `select_imap_folder` 返回 None,
抛出 `IMAP folder not found: folder=junk candidates=['[Gmail]/Spam', 'junk']`。

失败发生在 `read_refresh_messages` 的第二个文件夹上, 异常冒泡后整个账号这一轮收信被判失败,
**收件箱里已经读到的那批邮件也一起丢掉**, 所以中文 Gmail 账号是「整个账号收不到验证码」,
而不是「只有垃圾箱读不到」。实测 6 个 Gmail 账号里 4 个 (中文语言) 如此, 英文账号正常,
两者走同一个代理 —— 因此这不是代理问题。

## Decision

`imap/session/mailboxes.py` 按 RFC 6154 把逻辑名映射到 LIST 的特殊属性:
`sent→\Sent`、`drafts→\Drafts`、`deleted→\Trash`、`junk→\Junk`/`\Spam`、`archive→\All`/`\Archive`。
`select_imap_folder` 先照旧遍历候选名表, 表里全部失败后再调 `resolve_special_use_name`,
用服务器自己的名字 (LIST 返回的那个) 选一次。属性是协议层语义标签, 与账号语言无关,
所以 QQ/163/126 等本地化名字同样被覆盖。

## Alternatives considered

- **把各语言的名字补进候选表** — 一次改动就能让当前这批账号可用, 成本最低。否决:
  同一个 Gmail 在不同账号语言下名字不同, NetEase/QQ 系也各有本地化名, 这是无休止的枚举;
  属性解析一次覆盖所有语言与提供商。
- **每次选择都先 LIST 再选** — 少一次注定失败的候选名尝试。否决: 收件箱 (INBOX) 是唯一
  处处存在的名字, 走候选表零额外往返; LIST 只在候选表失败时才付一次, 常见路径不变慢。
- **什么都不做 / 复用现有** — 现有代码里 `mailboxes.py` 已经会解析 LIST 属性 (当时只为永久
  删除找 All Mail/Trash/Spam), 复用它的代价是零; 不做的代价是中文账号整账号收不到信。

## Consequences

中文及其它本地化 Gmail 账号的垃圾箱能读到了, 报错消失, 收件箱邮件不再被一起丢弃。
代价: 候选名表失败时多一次 LIST 往返; 服务器不返回特殊属性时行为与修复前一致 (仍然失败)。
`imap/session/mailboxes.py` 从「永久删除专用的 All Mail/Trash/Spam 解析器」变成通用的
逻辑名解析器 (`resolve_special_use_name` + `list_attributes`)。

## Testing

实测 (项目自身的连接代码 + 分组代理 `127.0.0.1:2334`, 只读): 对 6 个 Gmail 账号执行
LIST + SELECT, 修复前中文账号 `[Gmail]/Spam`→NO 且 `junk`→NO; 修复后同一账号由 `\Junk`
解析出 `[Gmail]/&V4NXPpCuTvY-` 并 SELECT OK, 英文账号仍走候选表命中 `[Gmail]/Spam`。
