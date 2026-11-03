# Agent Note: GitHub App 用 Manifest 一键创建, 实例先于 manifest 存在, state 一次性存库

Status: implemented

Decision-ID: github-app-manifest-flow

## Code

- `server/src/hx_email/server/router/providers/impl/github_manifest.py`
- `server/src/hx_email/api/impl/router/github_connect.py`
- `server/src/hx_email/models/messaging.py`
- `server/src/hx_email/api/impl/messaging/serializers.py`

## Problem

GitHub 实例原本要用户在 GitHub 上手建 App, 再把 App ID, Client ID, slug, PEM 私钥与 webhook secret 逐项抄回 HX-Email, 步骤多且容易抄错
GitHub 提供 App Manifest 流程: 把 manifest 表单 POST 给 GitHub, 用户点一次确认, GitHub 带一次性 code 跳回, 再用 code 兑换全部凭据
难点有三
- 入站端点按实例区分 `/api/v1/router/ingress/github/{instance_id}`, 而 manifest 里的 webhook 地址在建 App 时就写死了
- code 1 小时有效且只能用一次, 花掉之后若无法加密落库, App 已建出来私钥却丢了
- 回调来自浏览器跳转, 不一定带登录态

## Decision

- 管理员调 `GET /api/v1/router/github/manifest` 时先建 (或用 `instance_id` 复用) 一个 github 实例, manifest 的 webhook 地址带上这个 instance_id; `build_manifest(base_url, name_suffix, instance_id)` 比参考实现多一个参数就是为此
- manifest 权限只有 metadata=read, issues=write, pull_requests=write, 不写 contents 键; 事件只有 issue_comment, pull_request_review, pull_request_review_comment, issues; installation 两类事件默认投递, 写进 default_events 会被 GitHub 拒掉整个 manifest
- state 为 `secrets.token_urlsafe(32)`, 存 `router_github_app_states` 表并绑定 instance_id, 10 分钟有效, 回调以 `UPDATE ... WHERE used = 0 AND created_at > cutoff` 原子消费, 并发回调只有一个能赢
- 回调顺序固定为 密钥自检 -> 消费 state -> 花 code -> `seal_app_config` 加密写入该实例; 密钥不可用时 code 与 state 都不动; 兑换失败时 state 保持 used, 因为 code 一次性, 重试必须重新生成 manifest
- 兑换结果里的 client_secret 不落库, 本方案不启用 user-to-server 授权
- 回调成功 302 到 `/messaging?connected=1&slug=...&instance_id=...`, 失败 302 带 `error=<reason>`
- `verify` 用存下的私钥签 App JWT 调 `GET /app` 与 `GET /app/installations`; `attach` 先以 App 身份确认 installation 属于本 App, 再把 installation_id 记进实例配置
- 管理接口只返回 `has_private_key` 这类布尔; `/api/v1/messaging/instances` 的 `public_config` 也按 `SECRET_CONFIG_KEYS` 打码, 否则 GitHub 实例会把 PEM 回显给前端

## Alternatives considered

- 什么都不做 / 复用现有手填配置: 最强理由是零新增代码, 手填路径已经能用, 不引入新表. 否决原因是六项凭据逐项抄写容易出错, 私钥要先下载文件再粘贴, 违背一键接入的目标
- 一个全局 App, webhook 走不带 instance_id 的单一地址: 最强理由是与参考项目 HX-AI-Review 同构, 一个 App 可以服务多个 installation. 否决原因是现有入站端点, 验签与去重全部按 instance_id 定位, 全局地址要重写入站链路
- state 用 HMAC 签名不存库: 最强理由是无表, 服务重启与多 worker 天然可用. 否决原因是签名 state 在有效期内可重放, 做不到一次性消费, 并发两个回调都会去花同一个 code
- 先花 code 再检查密钥: 最强理由是少一次加解密自检. 否决原因是密钥不可用时 App 已建出而私钥无处可存, 只能去 GitHub 手动删 App

## Consequences

- 新增 `router_github_app_states` 表与 created_at 索引, 迁移幂等, 生成新 state 时顺手清理过期行
- 每次发起都会建一个 github 实例; 用户放弃创建时会留下一个未配置的空实例, 可在消息页删除
- 前端需要整页表单 POST 到返回的 `action`, 隐藏字段 `manifest` 为 manifest 的 JSON 字符串, 不能用 fetch
