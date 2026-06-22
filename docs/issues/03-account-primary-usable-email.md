# 添加邮箱账号时创建主可用邮箱

## What to build

实现邮箱账号添加的第一条完整业务路径。用户添加 Outlook 或 IMAP 邮箱账号后，系统自动创建对应的主可用邮箱，并在工作台中可见。账号和主可用邮箱都必须归属于当前用户，其他用户不可见。

## Acceptance criteria

- [x] 用户可以添加 Outlook OAuth 或普通 IMAP 邮箱账号的必要配置。
- [x] 每个邮箱账号创建时自动创建一个主可用邮箱。
- [x] 同一用户内可用邮箱地址唯一，不同用户可以各自添加相同邮箱地址。
- [x] 主可用邮箱在工作台中可列表展示、查看详情和停用。
- [x] 停用邮箱账号会使主可用邮箱不可继续作为可用资源使用。
- [x] 后端和前端测试覆盖多用户隔离与主可用邮箱创建。

## Completion

- 后端验证：`cd server && uv run pytest`
- 前端验证：`cd web && npm test && npm run build`
- 全仓验证：`npm test && npm run build`

## Blocked by

- #2
