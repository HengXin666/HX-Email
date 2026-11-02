# Agent Note: 临时邮箱可用域名支持手动删除, 被删除的域名不参与轮换

Status: implemented

Decision-ID: temp-mail-excluded-domains

## Code

- `web/src/features/settings/impl/temp_mail_domains.ts`

## Problem

系统设置 → 临时邮箱 → 可用域名 目前只有一条写路径: `POST /settings/cf-worker-sync-domains` 把
CF Worker `open_api/settings` 返回的域名整份覆盖写进 `cf_worker_domains`。用户无法表达
「这些域名我收到了, 但不要拿去注册」—— 例如某个域名在目标站点已被拉黑, 或收信延迟明显。
唯一的办法是手动改数据库, 而下一次同步又会把它写回来。

轮换的两处消费点是 `get_temp_mail_options()` (前端/外部 API 看到的候选域名与默认域名) 与
`CFWorkerTempMailProvider._default_domain()` (创建邮箱时真正落到 Worker 请求里的 `domain`)。
只要这两处都读同一份「同步结果」, 就没有地方能承载「收到但不使用」。

## Decision

新增设置项 `cf_worker_excluded_domains` (JSON 字符串数组, 默认 `"[]"`), 与 `cf_worker_domains`
正交: 前者是同步来的全集, 后者是用户的减法。域名比较统一 `lstrip("@")`, 因为 CF Worker 的
`open_api/settings` 返回的是 `@a.com` 形式。

- `temp_mail_options.py` 的 `get_temp_mail_options()` 输出 `domains = 同步域名 - 排除域名`;
  `default_domain` 若落在排除列表里则回退到剩余第一个, 全被排除则为 `""`。
- `cf_provider.py` 的 `_default_domain()` 跳过排除域名; 已同步的域名全部被排除时抛
  `TempMailProviderError`, 让创建失败得明确, 而不是静默交给 Worker 去挑一个用户已经否掉的域名。
  从未同步过域名 (列表为空) 时维持原行为: 返回 `""`, 由 Worker 用它的默认域名。
- `POST /settings/cf-worker-sync-domains` 同步成功后把排除列表里已不存在于新域名集合的项剪掉
  (域名被 Worker 下掉了, 留着只会变成幽灵项), 并在响应里返回 `excluded_domains`。
- `normalize_settings_updates` 校验该设置项必须是 JSON 字符串数组, 非法值按既有风格抛
  `ValueError` → `PUT /settings` 返回 422。

前端把删除/恢复写成对 `cf_worker_excluded_domains` 的本地编辑, 仍由「保存设置」统一 PUT —— 不新增
接口, 也不做「删除即生效」的隐式写。

## Alternatives considered

- **新增一个 DELETE/PUT 域名接口, 点删除即写库** — 交互更直接, 少一次「保存设置」。否决:
  设置页所有字段共用一套「本地编辑 + 统一保存」的语义, 单独一个立即生效的字段会让
  「我改了但没保存」和「我删了但没生效」同时存在; 而且要多一条写路径与它的鉴权/审计。
- **同步时直接把被删的域名从 `cf_worker_domains` 里抹掉** — 不需要新设置项, 数据只有一份。
  否决: 下一次同步必然把它写回来, 用户会认为「删了又自己长回来」; 而且抹掉之后就再也恢复不了
  (没有地方记得它曾经存在)。
- **让 Worker 侧删域名, 本实例只读结果** — 语义最干净, 单一事实来源。否决: 域名清单在
  Worker 的 `open_api/settings` 里是只读的公开端点, 本实例没有写权限, 用户也不一定拥有那个
  Worker; 把「哪些域名参与轮换」这个纯本地偏好推到远端, 会把一个设置页开关变成一次跨系统运维。
- **什么都不做 / 复用现有** — 用户当前只能改数据库且会被同步覆盖。否决: 用户明确提出
  「有的域名不希望参与轮换」, 这是产品需求而不是可以绕过的边角。

## Consequences

用户可以在设置页对单个域名做删除与恢复, 且删除结果跨同步保留; 排除列表里的域名不会出现在
默认域名下拉、不会被 `create_mailbox` 选中。代价: 设置项多了一个需要与 `cf_worker_domains`
保持一致的派生字段, 同步时要剪枝; 全部排除时创建会失败, 这条错误路径要显式提示而不是让
用户对着 502 猜。`get_temp_mail_options()` 与 `_default_domain()` 现在各自实现一遍过滤 ——
两处都在 `impl/temp_mail/` 内, 由同一份设置项驱动, 后续若再出现第三个消费点应抽成共享函数。

## Testing

`server/tests/test_cf_worker_provider.py` 覆盖 options 过滤与 `_default_domain` 跳过排除域名、
全排除时的报错; `server/tests/test_cf_worker_custom_auth.py` 覆盖同步剪枝与响应字段、以及
`PUT /settings` 对非法值的 422。前端由 `web/src/features/settings/tabs/TempMailSettingsTab.test.tsx`
覆盖删除/恢复写出的 `cf_worker_excluded_domains` 与默认域名下拉的收缩。门禁是
`bash scripts/verify.sh`。
