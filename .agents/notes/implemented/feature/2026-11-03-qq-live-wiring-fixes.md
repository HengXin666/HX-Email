# Agent Note: QQ 真机联调暴露四处接线缺陷, token 写全账号文件, 事件回传认 Authorization, OneBot 调用返回结构化结果, 读取兼容两种 chat_id

Status: implemented

Decision-ID: qq-live-wiring-fixes

## Code

- `server/src/hx_email/server/messaging/engine.py`
- `server/src/hx_email/api/impl/messaging/event_routes.py`
- `server/src/hx_email/server/router/impl/reader/page.py`
- `server/src/hx_email/server/router/bounds.py`

## Problem

前一篇路由网关决策 (`.agents/notes/implemented/feature/2026-11-02-messaging-router-gateway.md`) 的单测全绿, 但第一次把 NapCat 容器, 事件回传与路由层串起来真机收发时, 四处接线问题依次暴露. 它们都发生在容器内行为或两条写入路径的交界处, 单测里不存在.

1. token 永远校验不过. 引擎只写通用的 `config/onebot11.json`, 而 NapCat 登录后读写的是账号专属的 `onebot11_<uin>.json`. 账号专属文件里留着上一次的 access_token, 于是配置里明明写着新 token, 调用 OneBot HTTP 接口却得到:
   `{"message":"token verify failed!"}`
2. 事件回传全部 401. `POST /api/v1/messaging/events/qq` 原来只认 `X-Messaging-Token` 头, 但 OneBot 11 的 `httpClients` 只会发 `Authorization: Bearer <token>`, 没有配置自定义头的写法. 容器推来的每一条事件都被拒掉, 响应体是:
   `{"detail":"Invalid messaging event token"}`
3. 失败原因被抹平. `OneBotAdapter._call` 把所有失败压成一个 `MessagingError`, 文案只剩 `OneBot 请求失败: ...` 或 `OneBot 调用 send_private_msg 失败: ...` 这种字符串, retcode 丢了, "请求根本没发出去" 与 "发出去了但 OneBot 返回错误" 也分不开. 路由层的 outbox 要靠这两样决定重试, 终态还是风控信号, 拿到的却只有一句话.
4. 入库了却读不出来. `chat_id` 有两条写入路径且格式不一致: 事件端点 (`messaging/store.save_message`) 存纯号 `282000500`, 路由层 `store_inbound` 存完整地址 `qq:12:private:282000500`. reader 只按完整地址查, 于是事件端点写入的消息一条也读不出. 实测库里 `messaging_messages` 有 1 条, `read_messages` 返回 0 条.

## Decision

1. `QQEngineManager.start` 渲染一次 OneBot 配置, 先写 `onebot11.json`, 再覆盖 `config/` 下所有匹配 `onebot11_*.json` 的账号专属文件. 理由: 通用文件只在首次登录前起作用, 登录后 NapCat 只认账号专属文件, 只有两处都写才能让每次 start 设下的 token 真正生效. 账号专属文件不存在时 glob 为空, 行为与原来一致.
2. `receive_event` 同时接受 `X-Messaging-Token` 与 `Authorization` 两种头, 前者优先; `Authorization` 去掉 `Bearer ` 前缀后再比对, 不带前缀的原值也认. 理由: 自定义头是现有调用方在用的契约, 不能断; `Authorization` 是 OneBot 唯一能发的头, 不认它事件回传就无法工作. 校验逻辑仍是 `find_instance_by_event_token`, 安全强度不变.
3. `OneBotAdapter` 新增 `call_action(action, params) -> OneBotCallResult`, 从不抛异常, 返回 `transport` (`ok`, `timeout`, `connect_error`, `http_error`), `http_status`, `retcode`, `wording` 与原始 `data`. 理由: 路由层需要区分 "没发出去" (可安全重试) 与 "发出去后被拒" (按 retcode 判终态或风控), 这个区别只有在适配器里离 HTTP 调用最近的地方才拿得到. 原有 `_call` 与抽象基类 `MessagingAdapter` 的签名都不动, 老的前端路径照旧.
4. reader 查询单会话时用 `(chat_id = ? OR chat_id = ?)` 同时匹配完整地址与 `peer_of` 取出的纯号; `_row_to_envelope` 遇到不含 `:` 的纯号时, 用 `PLATFORM_OF_KIND` (目前只有 `qq`), 行内 `instance_id` 与 `chat_type` 补全成完整地址再解析. 理由: 两条写入路径都在用, 读端兼容是唯一不碰存量数据的做法. 补完这些逻辑后 `reader.py` 超过 300 行上限, 因此把三个 id 边界探测 `newest_id`, `oldest_id` 与 `ensure_no_gap_ahead` 下沉到新文件 `server/router/bounds.py`, 查询构造 `build_query` 与 `Source` 仍留在 reader.

`bounds.py` 与 `reader.py` 互相导入: reader 在模块顶层 import `bounds`, bounds 需要 reader 的 `Source` 类型与 `build_query`. 环靠两处断开: `Source` 只在 `if TYPE_CHECKING:` 下 import (配合 `from __future__ import annotations`, 运行时不求值), `build_query` 在 `newest_id` 与 `oldest_id` 的函数体内延迟 import. 任何一处提到模块顶层都会在导入期触发循环导入错误.

代表文件的选法: `server/src/hx_email/server/messaging/onebot.py` 的 `OneBotAdapter.call_action` 同样属于本决策 (第 3 处修复), 但它与 `engine.py` 同在 `server/messaging/` 目录, 门禁规定一条决策在每个直接父目录只能选一个代表文件, 所以 Code 只列 `engine.py`, `onebot.py` 的 `call_action` 上方用一段不含路径的注释指回本决策.
`bounds.py` 是本次新增文件, 与 `reader.py` 分属 `server/router/` 与 `server/router/impl/` 两个目录, 所以各列一行.
`event_routes.py` 的锚点放在外层 `def register_messaging_event_routes` 上方而不是 `receive_event`: `receive_event` 是外层函数体内第一条语句, Tree-sitter 会把它上方的注释挂到函数体之外, 门禁判为 anchor-position 错误.

## Alternatives considered

- 什么都不做: 最强理由是四处问题都只在真机联调时出现, 单测全绿, 手工删掉账号专属文件, 在容器里加反向代理改头, 只用路由层写入路径也能绕过去, 零代码改动. 否决原因是每一个绕法都要求每次部署或每次重新登录都人工介入, token 问题在每次扫码登录后都会复发, 而 QQ 通道的目标就是无人值守收发.
- 复用现有 `_call` 与 `MessagingError`, 在路由层解析异常文案取回 retcode: 最强理由是不新增接口, 适配器表面积最小. 否决原因是 `_call` 在 `raise_for_status` 与超时处根本不保留 retcode, 文案也不是稳定契约, 按字符串判断重试与风控既脆弱又会把 "没发出去" 误判成可重试之外的终态.
- 复用现有写入路径, 把事件端点改成也存完整地址, 并回填老数据: 最强理由是只剩一种格式, reader 不需要 OR 条件与补地址逻辑. 否决原因是老的 `/api/v1/messaging` 读取 (`messaging/store` 的 `list_messages`) 仍按 `chat_id = ?` 用纯号查, 回填会让这一侧读不出来; 存量纯号行无法回填, 两种格式必须共存.
- token 问题改成启动前删除 `onebot11_*.json`: 最强理由是只剩一个配置来源, 不需要 glob 覆写. 否决原因是账号专属文件里可能有 NapCat 自己写入的其它网络配置, 删除会丢失; 覆写与原通用文件写入同一份渲染结果, 行为可预期.
- 不拆 `bounds.py`, 申请把 `reader.py` 的行数上限放宽: 最强理由是没有循环导入. 否决原因是 300 行上限由 `scripts/check_arch.py` 全仓统一强制, 为一个文件开例外会让门禁失去意义; 边界探测与查询构造本来就是两个可分开的关注点.

## Consequences

- 循环导入是脆弱点. `bounds.py` 里的 `Source` 只能在 `TYPE_CHECKING` 块中 import, `build_query` 只能在函数体内 import; 谁把任意一处挪到模块顶层, 导入 reader 时就会报循环导入. 重构时把这两处当作承重结构.
- 纯号与完整地址两种 `chat_id` 格式要长期共存. 老数据无法回填, 事件端点与老前端仍写读纯号, 所以 reader 的 OR 条件与 `_row_to_envelope` 的补地址分支不能删; 删掉的直接后果是事件端点写入的消息再次读不出来.
- `COLUMNS` (以及 `BOUNDARY`) 在 `bounds.py` 与 `reader.py` 各留一份, 是为了不让 bounds 在模块顶层 import reader. 两份必须逐字一致: `newest_id` 与 `oldest_id` 用 `str.replace(COLUMNS, ...)` 把 reader 生成的 SQL 改写成 MAX 与 MIN 探测, 一旦两边列清单不一致, replace 静默失效, 探测退化成整行查询, 读 `newest` 或 `oldest` 列时报错.
- 补地址时平台名固定取 `PLATFORM_OF_KIND = "qq"`, 因为目前只有 QQ 走纯号写入路径; 以后别的平台若也经事件端点存纯号, 需要按实例的 kind 选平台名.
- 事件回传多认一种头之后, 任何能拿到实例事件 token 的人都可以用 `Authorization` 头推事件, 这与原来用自定义头的安全边界相同, 没有扩大.
- `engine.py` 正好 300 行, 本决策的锚点是把原来 start 函数体内的两行说明上移到 `def start` 正上方, 没有增加行数; 以后改这个文件要先腾出行数.

## Testing

这四处修复都是真机联调发现的, 现有单测 (`server/tests/test_router_core.py`, `test_router_qq.py` 等) 用的是假 OneBot 与内存库, 覆盖不到容器内 NapCat 读哪个配置文件, OneBot `httpClients` 实际发什么头, 以及两条写入路径交叉读写这些行为.

修复后的真机收发证据:

- 扫码登录成功, 账号 2242792762, 昵称 机器人SG, token 校验不再报 `token verify failed!`
- 经 `call_action` 调用 `send_private_msg` 发出私聊消息, 返回 `message_id` 1282981854
- NapCat 以 `Authorization` 头推送事件到 `POST /api/v1/messaging/events/qq`, 响应中 `stored=true`
- 同一条消息经 `read_messages` 读取返回 1 条, 与库中行数一致
