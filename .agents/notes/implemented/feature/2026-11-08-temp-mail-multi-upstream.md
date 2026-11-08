# Agent Note: 临时邮箱支持多个 CF Worker 上游, 上游 id 记在 provider_mailbox_id 里路由读信

Status: implemented

Decision-ID: temp-mail-multi-upstream

## Code

- `server/src/hx_email/server/mail/impl/temp_mail/upstreams.py`
- `server/src/hx_email/api/impl/settings/cf_worker_sync.py`
- `server/src/hx_email/server/settings_service.py`
- `server/tests/test_cf_worker_upstreams.py`
- `web/src/features/settings/impl/temp_mail_upstreams.ts`
- `web/src/features/settings/tabs/TempMailSettingsTab.tsx`

## Problem

临时邮箱只能配置一个 cloudflare_temp_email Worker: 凭证是三个单值键 `cf_worker_base_url` /
`cf_worker_admin_key` / `cf_worker_custom_auth`, 域名是全局的 `cf_worker_domains` /
`cf_worker_excluded_domains`, `CFWorkerTempMailProvider` 每次只读这一组。用户手里有多个 Worker
(各自不同的域名、Admin Key、PASSWORDS), 只能二选一。

难点不在建邮箱而在读信: `temp_mailboxes.provider_mailbox_id` 只存 `{"id","jwt"}`, 没有任何字段
说明它属于哪台 Worker。一旦配置变成多台, 已建邮箱就不知道该去哪台拉 `/api/mails`。

## Decision

- 新设置键 `cf_worker_upstreams`: JSON 数组, 每项 `{id, name, base_url, admin_key, custom_auth,
enabled, domains, excluded_domains}`, 整体进 `SENSITIVE_KEYS` 加密 (里面有 Admin Key)。
  `cf_worker_default_domain` 保留, 语义变为所有启用上游可用域名并集上的全局默认域名。
  排除列表从全局键变为每个上游一份 (原决策见
  `.agents/notes/implemented/feature/2026-10-19-temp-mail-excluded-domains.md`)。
- 迁移: 新键为空时 `upstreams.upstreams_from_values()` 把旧单值键读成 id 为 `default` 的一项;
  `GET /settings` 也按此兜底返回, 设置页第一次打开就看到它。任何一次带 `cf_worker_upstreams` 的
  `PUT /settings` 会同时清空旧键, 迁移就此完成, 删光上游也不会让旧键"复活"。未迁移前的同步继续写旧键。
- 建邮箱按域名路由 (`temp_mail_options.resolve_mailbox_target`): 请求的域名 (没给就用全局默认域名)
  归属哪个启用上游就交给它; 多个上游都提供同一域名时排在前面的胜出; 只被停用上游提供的域名返回 409;
  只有一个可用上游时, 未同步过的域名照旧交给它, 多个上游时未知域名返回 409。
- 读信按邮箱自己记的上游: 新建邮箱的 `provider_mailbox_id` 写成 `{"upstream", "id", "jwt"}`;
  缺 `upstream` 的老行 (含裸 jwt) 回退到 `default`, 再回退到第一个上游; 上游被删返回 503 并写明原因;
  上游停用只拦新建, 不拦读信。
- `provider = "cf"` 与 `temp_mail_providers["cf"]` 不变, 路由完全在 provider 内部完成, 表结构不动。
- `POST /settings/cf-worker-sync-domains` 增加 `upstream_id`: 只同步并剪枝该上游; 该上游尚未保存时
  只返回结果, 由设置页写进本地 state; 不带任何目标时依次同步所有启用上游。全局默认域名失效时依次
  回退到本次 Worker 的默认域名、并集第一个。
- 设置页每个上游一张卡片 (增删、上下移、启用开关、单独同步、单独删除/恢复域名), 仍走「本地编辑 +
  统一保存」, 不新增立即生效的写接口。

## Alternatives considered

- 新建 `cf_upstreams` 数据表: 结构更规范, 可以给每个上游加外键与审计。否决: 设置页所有字段共用
  「本地编辑 + 统一保存」, 独立表需要另一套 CRUD 接口与鉴权, 还要与 `PUT /settings` 的整份提交对齐;
  上游数量是个位数, JSON 设置键足够, 且天然复用敏感键加密。
- 每个上游注册成独立 provider (`temp_mail_providers["cf:<id>"]`, `temp_mailboxes.provider` 存 `cf:<id>`):
  读信路由天然正确, 不需要解析 `provider_mailbox_id`。否决: `"cf"` 在建邮箱路由、外部 API、验证码投递、
  实例同步合并多处硬编码, 还要迁移已有行的 `provider` 列; 把上游 id 塞进本来就是 JSON 的
  `provider_mailbox_id` 改动面最小。
- 保留单值键, URL 用逗号分隔: 零迁移。否决: 每台 Worker 的 Admin Key、PASSWORDS、域名排除都不同,
  逗号列表承载不了, 也无法给已建邮箱定位到具体一台。
- 什么都不做 / 复用现有: 用户只能在多个 Worker 间手动切换配置, 切走后旧邮箱全部收不到信。否决:
  这正是需求本身。

## Consequences

一个实例可以同时挂多台 Worker, 新邮箱按域名自动落到对的那台, 老配置和老邮箱无感迁移。代价:
`provider_mailbox_id` 的 JSON 多了 `upstream` 字段, 删除上游会让它名下的邮箱失效 (设置页删除前确认);
旧单值键要保留一个版本作为迁移来源, 之后再删; 同一域名被多台 Worker 提供时只看顺序, 不做负载均衡
或失败切换。

## Testing

`server/tests/test_cf_worker_upstreams.py` 覆盖按域名路由、共享域名按顺序、停用与排除、读信按上游、
老格式回退、上游删除、旧键兜底与保存后清空、`PUT /settings` 校验、单上游/未保存/全量同步。
`server/tests/test_cf_worker_provider.py` 与 `test_cf_worker_custom_auth.py` 继续覆盖单上游 (旧键) 行为。
前端由 `web/src/features/settings/impl/temp_mail_upstreams.test.ts` 与
`web/src/features/settings/tabs/TempMailSettingsTab.test.tsx` 覆盖。门禁是 `bash scripts/verify.sh`。
