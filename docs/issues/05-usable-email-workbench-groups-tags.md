# 建立可用邮箱工作台并沿用分组标签筛选

## What to build

实现第一阶段核心工作台。用户可以在统一列表中管理主邮箱、别名邮箱和临时邮箱，并沿用旧版 outlookEmailPlus 的分组、标签、搜索和分页整理能力。工作台是平台绑定、验证码读取和邮箱池操作的主要入口。

## Acceptance criteria

- [x] 工作台统一展示当前用户的主邮箱、别名邮箱和临时邮箱。
- [x] 支持按类型、状态、分组、标签、平台绑定情况和关键词筛选。
- [x] 分组和标签行为沿用旧版 outlookEmailPlus 的用户可见能力。
- [x] 列表支持分页或虚拟化，能承载大量邮箱数据。
- [x] 所有筛选只作用于当前用户数据。
- [x] 前端视觉参考 `ref/web` 的深色工作台风格，不复用旧项目前端。

## Completion

- 后端验证：`cd server && uv run pytest`
- 前端验证：`cd web && npm test && npm run build`
- 全仓验证：`npm test && npm run build`

## Blocked by

- #4
