# Agent Note: 拆分 messaging/routes.py, 实例详情支持 github_user

Status: implemented

Decision-ID: messaging-routes-split

## Code

- `server/src/hx_email/api/impl/messaging/routes.py`

## Problem

`api/impl/messaging/routes.py` 正好 300 行, 已到 arch-check 上限, 再加任何端点都会失败; 所在目录已有 5 个 .py, 也不能再平铺一个兄弟文件. 同时 `GET /api/v1/messaging/instances/{id}` 对 `github_user` 实例返回 400 "Messaging kind 'github_user' is not available yet": 该平台只经 gh CLI 轮询与路由网关工作, 注册表里没有 adapter, 而详情接口要求先拿到 adapter. 列表接口用 `safe_adapter` 能列出它, 但不带 capabilities.

## Decision

- 实例相关端点下沉到子包 `api/impl/messaging/instances/`: `lifecycle.py` (catalog, 列表, 建, 详情, 删, connect, config, disconnect), `login.py` (login, login/probe, login/status), `engine.py` (内置引擎 start, stop, refresh-qr, login/qr 与 `port_from_config`). `routes.py` 只保留 `register_messaging_routes`, 按原顺序依次注册三组, 对外入口与导入路径不变. 拆分前后对同一个 `APIRouter` 注册出的 15 条路由 (方法, 路径, 状态码, 顺序) 逐条比较一致.
- 详情接口改用 `serializers.instance_detail`: `github_user` (集合 `CATALOG_DETAIL_KINDS`) 不再要 adapter, 返回实例本身加注册表目录里声明的 capabilities; 状态就是 setup 检查写入的 `online` / `error`. 配置照常经 `public_config` 脱敏, 打码集合不变 (配置里本就没有 token, 误写入的 `event_token` 等仍打码). 其它没有 adapter 的平台 (如 `qqbot`) 行为不变, 仍是 400.
- connect, login 等会话型接口对 `github_user` 仍返回 400: 它没有会话, 接入与重新检查走 `/router/github_user/save` 与 `/check`.

## Alternatives considered

- 什么都不做, 等下次真要加端点时再拆: 最强理由是零改动, 现在 arch-check 仍然通过. 否决: 文件正好 300 行, 补 github_user 详情本身就要动它, 不拆就加不进任何一行; 详情 400 也是前端已经能触发的现存问题.
- 复用现有方案, 让前端改从 `/router/sources` 或 `/router/github_user/check` 取 github_user 的状态: 最强理由是后端不用改. 否决: `/check` 每次都会真的调用 gh CLI 并改写状态, 不适合当只读详情; `/sources` 不带脱敏配置与 capabilities, 前端要为一个平台单独拼数据.
- 给 `github_user` 补一个像 `GitHubAppAdapter` 那样的薄 adapter: 最强理由是所有 `/messaging/instances/{id}/...` 接口一次都能用. 否决: `gateway/impl` 已有 5 个 .py, 加文件要再拆目录; 而且 connect, login 对 gh CLI 账号没有含义, 造一个只会让前端出现无效按钮; 详情只需要目录里已有的能力声明.
- 把 `engine` 一组搬进 `messaging/` 目录平铺: 最强理由是改动最小. 否决: 目录会变成 6 个 .py, arch-check 不过.
- 在 `require_instance` 里对 `github_user` 放行: 否决, 会让 connect, login 等接口拿到 None adapter, 失败点更隐蔽.

## Consequences

- 用例 `server/tests/test_router_github_user.py::test_instance_detail_over_messaging_rest`: 检查通过的实例详情返回 200, 状态 `online`, 登录名与仓库可见, 误写入的 `event_token` 打码, capabilities 与目录一致; 不存在的 id 为 404; login 仍为 400.
- `PUT .../config` 修改 `cli` 后不会自动重新检查, 仍需调用 `/router/github_user/check` (本次未做).
