from __future__ import annotations

# 刷新覆盖的文件夹: 收件箱 + 垃圾邮件箱。
# 不少站点 (freebuff/github 等) 的验证码会被 Outlook/Gmail 判成垃圾,
# 只刷收件箱会永远收不到码 (2026-09-09 实测)。
REFRESH_FOLDERS: tuple[str, ...] = ("inbox", "junk")
REFRESH_FOLDER_TOP: int = 200
