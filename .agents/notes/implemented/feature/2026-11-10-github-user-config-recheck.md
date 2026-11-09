# Agent Note: github_user 通过 PUT config 改 CLI 路径或仓库时立即重新检查

Status: implemented

Decision-ID: github-user-config-recheck

## Code

- `server/src/hx_email/api/impl/messaging/instances/lifecycle.py`

## Problem

`github_user` 实例的 `cli` 与 `repository` 只能经 `/router/github_user/save` 设置: 那里仅管理员可用, 先做格式检查, 保存后跑 setup 检查并据结果置 `online` / `error`. 但通用的 `PUT /api/v1/messaging/instances/{id}/config` 也能写这两个键, 而且不检查: 改成不存在或相对路径的脚本后实例仍是 `online`, 轮询与出站会拿新路径直接执行, 直到下次手动 `/check` 才暴露; 请求还能顺手写入 `login`, 而 `login` 决定 `from_self` 与 `mention_self`.

## Decision

- `PUT .../config` 对 `github_user` 实例: 忽略请求里的 `login` (只由检查写入); `cli` 或 `repository` 去掉首尾空白后与现值不同时, 视同重新接入: 要求管理员, 先用 `config_problem` 做与 save 相同的格式校验 (失败 400, 不写库), 写库后调用 `/router/github_user` 同一个 `run_check`, 返回 `{success, report, instance}`, 状态与登录名按检查结果更新.
- 只改其它键 (observe 开关, `poll_seconds`, `disabled_actions`) 时行为不变, 不跑检查, 返回里没有 `report`.
- `run_check` 与 `KIND` 从 `api/impl/router/github_user_routes.py` 下沉到 `api/impl/messaging/instances/github_user.py`, 两个入口共用; 直接从路由模块导入会形成 `messaging` 与 `router/github_user_routes` 的循环导入.
- 处理函数改为 `async`, 因为 `run_check` 是协程; 其它平台的分支与返回不变.

## Alternatives considered

- 什么都不做, 要求前端改完路径后自己再调 `/check`: 最强理由是后端不动. 否决: 中间窗口里实例仍是 `online`, 轮询会执行未检查的新路径; 也挡不住非 save 路径写入 `login`.
- 复用现有方案, 在 `PUT config` 里对 `github_user` 直接拒绝 `cli` / `repository`, 只允许走 save: 最强理由是只有一个入口. 否决: save 不带其它键, 前端改路径要拆两次请求; 改为复用 save 的同一套校验与检查, 两个入口结果一致.
- 只把状态置为 `error` 等下次手动检查: 否决, 管理员刚改完就要知道新路径能不能用, 检查本身只读且有超时.

## Consequences

- 用例 `server/tests/test_router_github_user.py::test_config_cli_change_rechecks`: 只改 observe 开关不检查且伪造的 `login` 被忽略; 相对路径 400; 改到不存在的脚本得到 `cli_not_found`, 状态 `error`, 登录名清空; 改回原路径 (带空白) 后检查通过回到 `online`, 其它配置保留.
- 改路径的请求会同步等待一次 gh 调用 (setup 检查自带超时).
