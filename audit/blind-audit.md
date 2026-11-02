# HX-Email 三笔提交盲审 完整版

审计对象为 main 上的 `8d1849c`, `938e199`, `c22c4aa`, 基线为 `c1eda91`, 审计时间 2026-11-02 23:05 CST
证据全部来自在沙箱中由映射 `.git` 重建的仓库 (main=c22c4aa) 上的实测, 未改动映射目录中除 `audit/` 以外的任何文件

## 1. 结论

| 提交 | 结论 | 阻塞级发现 |
| --- | --- | --- |
| `8d1849c` chore(notes) 门禁入口与 v2 配置 | 有保留地 OK | F1 CI 仍调用已删除脚本, F3 待审项也让退出码为 1 且 NOTE-EXEMPT 已失效 |
| `938e199` feat(temp-mail) 可用域名手动删除 | 有保留地 OK | 无阻塞, 最高为 F4 显式地址绕过排除 (高) |
| `c22c4aa` docs(messaging) 路由网关决策与规格 | 坏 (作为实现规格不可直接开工) | F10 三份文档会话地址三套语法, F11 出站幂等与重发规则互相矛盾, F12 NapCat 512 MB 上限低于自家实测与目标 |

- 本地门禁入口确已修好, 但 CI 门禁仍坏, 且当前 main 全量门禁有 12 项错误与 72 项待审, 任何触碰受保护目录的提交都会被挡
- 临时邮箱功能主路径正确, 前后端测试都能测到真行为, 剩余问题集中在归一化与显式地址这两条边界
- 消息路由文档单看 ADR 自洽度尚可, 但与同批 `docs/providers/*.md` 在地址, 幂等, 限流, 内存四处直接冲突
- 相比最小版, `c22c4aa` 的结论由 "初判有保留地 OK" 下调为 "坏", 原因是补做 B 组核实后发现 F10 到 F12

## 2. 发现表

| 编号 | 级别 | 文件:行 | 一句话 |
| --- | --- | --- | --- |
| F1 | 阻塞 | `.github/workflows/agent-notes.yml:43` | CI 仍执行 `.agents/skills/hx-agent-notes/scripts/verify-all.ts`, 该文件已在 af7eb02 搬走, 8d1849c 未同步 |
| F2 | 阻塞 | `.agents/notes/proposed/feature/2026-11-02-messaging-router-gateway.md:9` | c22c4aa 的 proposed note 引用三个找不到 AST 锚点的文件, 模拟暂存 3 错 3 待审 |
| F3 | 阻塞 | `.agents/skills/hx-agent-notes/scripts/redline/verify.py:78` | `ok=not issues` 让待审项也判失败, 72 个未建 note 目录的任何改动都被挡 |
| F3b | 阻塞 | `AGENTS.md:55` | 文档仍指引写 `NOTE-EXEMPT.md` 豁免, 新门禁把它判为 note-format 错误 |
| F4 | 高 | `server/src/hx_email/server/temp_mail/cf_provider.py` | `create_mailbox("me@a.com")` 在 a.com 已排除时仍把该域名发给 Worker |
| F5 | 中 | `server/src/hx_email/server/settings_service.py` | 归一化只做 `lstrip("@")` 不做小写, `a.com` 排不掉 `A.com`, 剪枝时又静默删掉大小写不同的项 |
| F6 | 中 | `server/src/hx_email/server/temp_mail/cf_provider.py` | 默认域名不在同步列表内时 options 与 create 仍使用它 |
| F7 | 低 | `server/src/hx_email/server/settings_service.py` | 排除列表接受空串, 纯空白, `@` 与重复项, 剪枝后重复仍保留 |
| F8 | 低 | `server/src/hx_email/api/impl/temp_mail` | 全部排除时 options 返回空, create 返回 502, API 调用方得不到 4xx 语义 |
| F9 | 低 | `docs/ref_api.md` | cf-worker-sync-domains 响应描述漏了 `message` 字段 |
| F10 | 高 | `docs/messaging-router.md:60` | 会话地址在 spec, `qq-napcat.md:130`, `github-app.md:111` 中是三套互不兼容的语法 |
| F11 | 高 | `docs/messaging-router.md:382` | 重启把 sending 回退为 queued 会重发, 与 `qq-napcat.md:195` 的超时不自动重发相反, ADR:161 的幂等键还少了 kind |
| F12 | 高 | `docs/adr/0005-messaging-router-gateway.md:180` | A5 要求 NapCat `--memory=512m`, 而 `qq-napcat.md:237` 估算约 500 MiB, 目标 p95 700 MiB |
| F13 | 中 | `docs/adr/0005-messaging-router-gateway.md:177` | A2 每分钟唤醒不超过 2 次, 但 3 条 SSE 各 25 秒心跳加邮件轮询默认 30 秒已远超 |
| F14 | 中 | `docs/adr/0005-messaging-router-gateway.md:84` | webhook 重试 8 次从 2 秒翻倍约 8.5 分钟用尽, 与 "24 小时 dead" 及阶段 3 停机 1 小时补投矛盾 |
| F15 | 中 | `docs/messaging-router.md:174` | envelope 的 reply_to, occurred_at, attachments, is_self 在 `messaging_messages` 无列, 迁移也未加列 |
| F16 | 中 | `docs/messaging-router.md:108` | 示例 `occurred_at` 写成本地化时间串, 与字段定义 ISO 8601 UTC 不符 |
| F17 | 中 | `docs/messaging-router.md:197` | `router_outbox.instance_id NOT NULL`, 但 webhook 投递属于 route 且可跨实例 |
| F18 | 中 | `docs/messaging-router.md:407` | QQ 限流每日 1000 无每小时项, `qq-napcat.md:173` 为每日 2000 加每小时 300, 单条长度 4000 对 1500 |
| F19 | 中 | `docs/messaging-router.md:179` | 入站去重是永久唯一索引, `qq-napcat.md:197` 要求 10 分钟窗口, 部分索引无法表达窗口 |
| F20 | 低 | `docs/adr/0005-messaging-router-gateway.md:186` | GitHub 回调路径与 `github-app.md:213` 不同, 事件集与权限集也与 `github-app.md:96` 不一致 |
| F21 | 低 | `docs/messaging-router.md:219` | delivery 有 `poll` 而 ADR:47 只有三种, `manual_hold` 与 `channel` 无定义, delivery_status 的第二种查法无 REST 对应 |
| F22 | 低 | `server/src/hx_email/server/messaging/types.py:142` | `send_message(target, text)` 无 reply_to 也无错误分类, "不改签名的薄包装" 给不出 SendResult 所需字段 |
| F23 | 低 | `docs/adr/0005-messaging-router-gateway.md:191` | ADR 与 spec 中 0 处 "需复核", 但 GitHub 写限额等外部数字未注明来源 |
| F24 | 低 | `docs/messaging-router.md:385` | 未规定消息保留期, raw 落盘文件清理与 SQLite 写并发 |
| F25 | 中 | `.agents/skills/hx-agent-notes/SKILL.md:36` | SKILL.md, verify.md, pre-commit 资产, install.py 仍写 `scripts/redlines/agent_notes.py` |
| F26 | 低 | `.agents/notes.config.json:1` | v1 到 v2 迁移丢了 tests 与 md 的豁免语义, commit message 只说保留五个目录 (推断) |
| F27 | 低 | `.agents/skills/hx-agent-notes/scripts/redline/run.ts:1` | 只导出 `runGate` 无顶层调用, 直接 `node run.ts` 静默退出 0 |
| F28 | 低 | `web/src/pages/Settings.tsx:59` | 删除只改本地状态需点保存, 同步按钮直写服务端, 未保存的删除可能被同步响应覆盖 (推断, 未实测) |
| F29 | 低 | `web/tsconfig.app.tsbuildinfo` | 构建产物已被跟踪, 由 a156075 引入, 不属于三笔 |

## 3. 分组证据

### A 组 临时邮箱排除域名 938e199

- A1 对齐: 后端 options, create, sync 剪枝, settings 写入四处都读同一个排除列表, 与 note 的 Decision 段一致
- A1 写入: `normalize_domain_list` 拒绝对象与含非字符串项的数组, PUT /settings 返回 422, 由新增测试覆盖
- A2 大小写: 用 probe 设置排除 `a.com`, 同步列表 `A.com`, options 仍返回 `A.com`, 剪枝时把 `a.com` 删掉, 见 F5
- A2 显式地址: 排除 a.com 后调用 `create_mailbox("me@a.com")`, 发给 Worker 的 `domain=a.com`, 见 F4
- A2 幽灵默认: `cf_worker_default_domain=stale.com` 不在同步列表内, options 与 create 都用 `stale.com`, 见 F6
- A2 脏数据: 排除列表写入 `["", " ", "@", "a.com", "a.com"]` 全部被接受, 剪枝结果保留重复, 见 F7
- A2 读端容错: 非法 JSON 与对象类型在读取时安全回落为空列表, 不会让 options 报错
- A3 全部排除: options 返回 `domains=[]` 且 `default=""`, create 抛 `TempMailProviderError` 映射为 502, 见 F8
- A3 前端: `TempMailSettingsTab.tsx` 在可用列表为空时显示警告文案, UI 层有提示
- A4 写入时机: `Settings.tsx:59` 的 `setSetting` 只改本地状态, `Settings.tsx:66` 在点保存时才整体 PUT
- A5 后端测试: 938e199 上 25 passed, 把新测试放到 8d1849c 的 server/src 上运行, 新增 7 条中 6 条失败
- A5 前端测试: `TempMailSettingsTab.test.tsx` 在 938e199 上 5 passed, 换回 8d1849c 的组件后 5 条全部失败
- A6 文档: `docs/ref_api.md` 的同步响应示例与实际返回只差 `message` 字段, 见 F9

### B 组 消息路由文档 c22c4aa

- B1 地址: spec 用 `qq:<instance_id>:group:<gid>`, qq-napcat 用 `qq:<self_id>:g:<peer>` 并有临时会话 `t`, github-app 用 `owner/repo#number` 且 chat_type 为 group, 见 F10
- B1 幂等: ADR:161 出站键为 `(instance_id, idempotency_key)`, note:44 与 spec:209 为 `(instance_id, kind, idempotency_key)`
- B1 幂等: qq-napcat:194 要求调用方传 UUID v4 的 `client_msg_id`, 24 小时窗口, 状态含 `duplicate`, spec:271 是 8 到 64 字符的 `idempotency_key` 且无 duplicate 状态
- B1 重发: spec:382 承认重启会重发且 "QQ 与 GitHub 都没有平台侧幂等键", 而 github-app:149 用正文隐藏 `op_id` 标记查重, 见 F11
- B1 信封: github-app:118 说统一信封就是现有 `MessagingMessage` 且不扩展字段, spec 3.1 定义了 16 个字段的新信封
- B2 schema: 唯一索引列 `message_id` 与现表 `models/messaging.py:39` 一致, 部分索引 `WHERE message_id <> ''` 在 SQLite 中合法
- B2 schema: 现表只有 sender_id, sender_name, text, message_id, raw_json 等列, 信封的 reply_to, occurred_at, attachments, is_self 无处可存, 见 F15
- B2 schema: `router_outbox` 用 instance_id 作外键与唯一键前缀, kind=webhook 的行属于 route, 跨实例前缀订阅没有合法 instance_id, 见 F17
- B2 tool: 11 个 MCP tool 均为 `additionalProperties: false`, 与 commit message 的 11 个一致
- B2 tool: `messages_pull` 把 cursor 设为必填, 却又说 "为空则从 session_select 给出的位置读", 服务端没有保存这个位置的设计
- B3 registry: `registry.py:24` 与 `registry.py:51` 确实仍写 lagrange-python, ADR:34 的描述属实
- B3 目录计数: `server/messaging/` 5 个, `server/messaging/impl/` 5 个, `api/impl/messaging/` 5 个, `models/` 5 个, spec:12 到 14 的计数属实
- B3 去重与读取: `messaging_messages` 只有 `(instance_id, chat_id, id)` 普通索引, `store.py:169` 与 `store.py:178` 只做 `ORDER BY id DESC LIMIT`, ADR 的缺口描述属实
- B4 内存: A5 的 512 MB 上限低于 qq-napcat:237 的约 500 MiB 估算加余量, 低于 qq-napcat:265 的 p95 700 MiB 目标, issue 556 记录 800 MB 以上, 见 F12
- B4 后果: 容器触顶被 OOM 杀掉后重启会重新登录, 这正是 ADR 自己列为最高优先级的风控风险
- B5 A1 与 A2: 测量对象是整个后端进程, 而 `fetch/scheduler.py:135` 的邮件轮询默认 30 秒, 加上 spec:365 的 SSE 25 秒心跳, A2 在路由层出现前就无法通过, 见 F13
- B5 A3: "启用与未启用路由网关" 需要开关, 配置表中没有对应键
- B5 A4 与 A6: 数字可测, 但 A6 未给入站速率, 结果不可复现
- B5 重试: ADR:162 规定退避上限 15 分钟最多 5 次, ADR:84 规定 webhook 重试 8 次与 24 小时 dead, spec:440 要求停机 1 小时后补投, 三者不能同时成立, 见 F14
- B6 漏项: 无消息保留期与清理, 无 raw 落盘文件回收, 无 SQLite 写锁与 busy_timeout 说明, 无路由 API Key 的生成与吊销接口, 见 F24
- B6 漏项: GitHub 事件集 ADR:189 为四个, github-app:96 到 103 还订阅 `pull_request_review`, `push`, `installation`, 权限还含可选 Contents, 见 F20
- B6 门禁: proposed note 引用的三个文件找不到锚点, 产生 3 项 anchor-cardinality 错误, 结构也不是 proposed 模板的 Problem, Proposal, Acceptance criteria, Risks, 见 F2

### C 组 门禁 8d1849c

- C1 脚本: package.json 的 9 条 notes 脚本指向的文件都存在于 `cli/` 与 `authoring/`
- C2 配置: `.agents/notes.config.json` 只含 version 2 与五个 guarded 目录, 五个目录都存在
- C3 无改动: `node .../cli/verify-all.ts --staged` 在无暂存时退出 0
- C4 全量: `--all` 退出 1, 12 项错误, 72 项待审, 错误为 note-format 3, anchor-position 2, note-path 2, ast-parse 2, anchor-cardinality 3
- C4 能拦: 只改 README 通过, 服务端无 note 改动退出 1, 改 `ApiAccess.tsx` 注释退出 1, 改 `messaging/types.py` 退出 1
- C4 豁免: 按 `AGENTS.md:55` 写 `.agents/notes/NOTE-EXEMPT.md` 后再改服务端, 输出 1 错 1 待审, 豁免文件本身被判 note-format, 见 F3b
- C5 入口: `redline/run.ts` 无顶层调用, 真正入口 `cli/verify-all.ts` 会原样传出 verify.py 的退出码, 见 F27
- C6 CI: 工作流第 43 行仍指向旧路径, 本地修好而 CI 未修, 见 F1
- C7 文档: SKILL.md, `references/verify.md`, `assets/hooks/pre-commit`, `install.py` 仍写旧脚本路径, 见 F25
- C8 commit message 自述 "旧钩子退出码 2" 与 "v1 配置被 gate-error 拒绝" 均实测属实

### D 组 全局

- D1 产物: 三笔 diff 中没有 `.hark-report-*`, tsbuildinfo, pyc 等产物, 仓库中已跟踪的 tsbuildinfo 来自更早的 a156075, 见 F29
- D2 留坑: 三笔各自模拟暂存的门禁结果为 938e199 3 错 10 待审, c22c4aa 3 错 3 待审, 8d1849c 在 af7eb02 上 6 错 76 待审
- D2 留坑: 当前 main 的状态让下一位改动受保护目录的人必然被挡, 且没有可用的豁免通道
- D3 message: 8d1849c 与 c22c4aa 的 message 与 diff 相符, 938e199 的 message 称前端 "仍由保存设置统一 PUT" 只覆盖删除与恢复, 不覆盖同步按钮

## 4. 核实后排除的假问题

- X1 怀疑 8d1849c 夸大 "旧钩子每次提交退出码 2", 实测旧钩子在 af7eb02 上退出 2 并报 Failed to spawn, 属实
- X2 怀疑 "v1 配置会被新门禁拒绝" 是臆测, 实测 af7eb02 上 verify.py 报 gate-error 并退出 2, 属实
- X3 怀疑门禁 `--staged` 退出 0 是放水, 实测有违规时退出 1, 无暂存时 0 是正常行为
- X4 怀疑 ADR 关于 registry.py 仍写 lagrange-python 的说法不实, `registry.py:24` 与 `:51` 证实属实
- X5 怀疑 spec 的目录文件数核对算错, 四个现有目录实数均为 5, 新增目录规划均在 2 到 5 之间
- X6 怀疑 938e199 的测试只是快照式空测, 后端 7 条中 6 条与前端 5 条全部在旧代码上失败, 测的是真行为
- X7 怀疑三笔夹带构建产物, diff 中没有, 仓库内的 tsbuildinfo 是更早提交引入

## 5. 我无法核实的事项

- 调用方机器上 `.git/hooks` 是否已由 lefthook 安装, 以及 node, uv, lefthook 的实际版本
- web 端 playwright 端到端用例, 只运行了 vitest 单测
- NapCat 仓库提交数, 镜像标签 v4.18.28, 第三方实测内存数据, issue 556 与 go-cqhttp issue 2471 的原文
- GitHub installation token 有效期, App 主速率上限与二级速率限制阈值的当前官方数字
- NapCat 上报是否携带 `X-Messaging-Token` 头, 以及 message_id 在容器重启后是否复用
- F28 未保存删除与同步按钮交互的实际表现, 仅由代码推断

## 6. 如果只能修三件事

1. 门禁可用性: 把 `.github/workflows/agent-notes.yml:43` 改到 `cli/verify-all.ts`, 让待审项不改变退出码或恢复 NOTE-EXEMPT 通道, 并清掉 main 上的 12 项错误
2. 消息路由文档统一: 以一份文档为准统一会话地址, 出站幂等键与重发规则, 限流参数, 并把 NapCat 内存上限改到不低于实测 p95
3. 临时邮箱边界: create 时对显式地址的域名同样执行排除校验, 排除列表与同步列表统一小写并去重, 默认域名必须属于同步列表
