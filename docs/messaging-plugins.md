# 消息插件（Messaging Plugins）

HX-Email 定位升级：在邮箱收发之外，以**插件模式**接入即时消息平台的收发，
并提供与邮箱一致的统一抽象协议。本功能不是主功能（产品名仍为 HX-Email），
因此按需激活：用户添加并启用某个平台的插件实例后，才启用对应能力。

## 1. 平台调研结论

### 1.1 QQ

- **主流实现**：`NapCatQQ`（[github.com/NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ)，
  基于 NTQQ 的现代协议端，活跃维护、~10k stars，提供 OneBot 11 兼容 HTTP/WS 接口与 WebUI）。
- **备选**：`Lagrange.OneBot`（C# 实现的 NTQQ 协议端，同样暴露 OneBot 11 API）。
- **不推荐**：`go-cqhttp`（已停止维护，2023 年后不再跟进 NTQQ 协议，登录与风控问题多）。
- **登录与风控**：个人号走第三方协议存在**封号/风控风险**，官方对扫码登录、异地登录、
  消息频率均有风控。NapCat 的 WebUI 支持扫码登录，登录态持久化在本地 NTQQ 数据目录，
  可长期维持。降低风险的做法：专用小号、控制发送频率、避免营销/高频消息。
- **能力**：私聊、群聊收发；群列表/群成员/踢人/禁言/全体禁言/退群等群管理操作；历史消息。

### 1.2 微信

- **个人微信**：`wechaty` / 各类协议模拟（如 GeweChat、padlocal 等）依赖非官方协议，
  **封号风险高**，且 Web 协议多已被官方禁用，稳定性差。
- **官方通道**：**企业微信（WeCom）API**，机器人消息、群机器人、客户联系等能力官方支持，
  风险低，但能力边界与企业微信账号绑定，不等于个人微信。
- **结论**：插件目录中保留 wechat 占位，接入时默认引导企业微信官方 API；
  个人微信方案仅作高级选项并显著提示风险。

### 1.3 Telegram

- **官方 Bot API**：`python-telegram-bot`（官方推荐的 Python 封装），支持 long polling /
  webhook，机器人账号由 @BotFather 创建，**零账号封禁风险**。
- **能力**：私聊、群组、超级群、频道收发；管理员操作（踢人/禁言/置顶/公告）。

### 1.4 Discord

- **官方 Bot API**：`discord.py`，机器人经 Developer Portal 创建并邀请入服务器。
- **能力**：私信、文字频道、语音频道；服务器管理（踢人/禁言/频道权限）。
- 个人账号自动化违反 Discord ToS，**只支持官方机器人账号**。

## 2. 统一抽象设计

所有平台适配器实现同一个抽象接口，业务层/API 层只面对抽象类型，
保证 QQ/微信/TG/Discord 未来的 API 形态一致。

### 2.1 核心概念

| 概念                    | 说明                                                                |
| ----------------------- | ------------------------------------------------------------------- |
| `MessagingInstance`     | 一个用户的一个平台连接实例（如一个 QQ 号），含配置与状态            |
| `MessagingAdapter`      | 平台适配器：登录/状态/收发/群组操作的统一接口                       |
| `MessagingMessage`      | 统一消息信封：direction / chat_id / chat_type / sender / text / raw |
| `MessagingConversation` | 会话：私聊（friend）或群聊（group）                                 |
| `MessagingGroup`        | 群/频道，附能力位标记可执行的管理操作                               |
| `Capabilities`          | 能力位：qr_login / groups / history / risk_level                    |

### 2.2 适配器接口（`server/messaging/types.py`）

```python
class MessagingAdapter(ABC):
    kind: str                    # "qq" | "wechat" | "telegram" | "discord"
    capabilities: Capabilities   # 能力位

    def start(self) -> None: ...          # 连接/心跳（QQ 为 HTTP API 探测）
    def stop(self) -> None: ...           # 停止
    def status(self) -> AdapterStatus: ...  # online/offline/error + 账号信息
    def create_login(self) -> LoginTicket: ...  # 扫码/授权引导
    def check_login(self) -> LoginState: ...
    def send_message(self, target: MessageTarget, text: str) -> str: ...
    def list_conversations(self) -> list[MessagingConversation]: ...
    def list_messages(self, conversation_id: str, limit: int = 50) -> list[MessagingMessage]: ...
    def list_groups(self) -> list[MessagingGroup]: ...
    def group_action(self, group_id: str, action: GroupAction) -> bool: ...
```

- `MessageTarget = { chat_id, chat_type }`，`chat_type ∈ private | group | channel`。
- `GroupAction = { kick: member_id } | { ban: member_id, duration } | { unban: member_id }
| { mute_all } | { unmute_all } | { leave }`。
- 适配器不要求平台原生实现全部能力：`Capabilities` 明确标注支持范围，
  API 对不支持的操作返回 501/明确错误。

### 2.3 事件流

- **推送模式（QQ/OneBot）**：NapCat 将事件 POST 到本服务
  `POST /api/v1/messaging/events/{kind}`，携带实例级 `X-Messaging-Token`，
  服务落库后可通过 REST 查询（“像收邮件一样读消息”）。
- **拉取模式（TG/Discord 未来）**：adapter 后台线程轮询/长连接写入同一消息表。

### 2.4 登录态长期维持

- QQ：扫码在 NapCat WebUI 完成，登录态由 NapCat/NTQQ 本地持久化；
  HX-Email 只管理连接与业务，不保存 QQ 密码/票据（最小化泄露面）。
- TG/Discord：Bot Token 由官方管理，服务端加密存储 token。

### 2.5 零配置使用路径（QQ）

用户视角只有三步：**添加 → 扫码 → 使用**，不暴露任何协议细节：

1. 点击「添加 QQ」，后端自动创建实例并填入 NapCat 本地默认地址
   （`http://127.0.0.1:3000` OneBot HTTP、`http://127.0.0.1:6099/webui` 登录页），
   同时自动生成实例级事件 Token；
2. 页面直接弹出内嵌 NapCat 登录页（即二维码），手机 QQ 扫码即完成登录；
3. 登录后即可查看会话、收发消息、管理群组。

- 前端不再要求填写 api_base_url / webui_url / event_token 等字段；
- `event_token` 等敏感配置在 API 返回中脱敏（`***`），仅服务端持有；
- 若 NapCat 部署在非本机默认端口，可在实例配置接口中按需覆盖。

## 3. 数据模型

```sql
messaging_instances (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL,              -- qq / wechat / telegram / discord
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'stopped',  -- stopped/connecting/online/error
  config_encrypted TEXT NOT NULL DEFAULT '',  -- 整体加密的 JSON 配置
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)

messaging_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id INTEGER NOT NULL REFERENCES messaging_instances(id),
  direction TEXT NOT NULL,         -- inbound / outbound
  chat_id TEXT NOT NULL,
  chat_type TEXT NOT NULL,         -- private / group / channel
  sender_id TEXT NOT NULL DEFAULT '',
  sender_name TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL DEFAULT '',
  message_id TEXT NOT NULL DEFAULT '',
  raw_json TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
```

## 4. REST API（前缀 `/api/v1/messaging`）

| 方法   | 路径                                  | 说明                                        |
| ------ | ------------------------------------- | ------------------------------------------- |
| GET    | `/catalog`                            | 插件目录（四种平台 + 能力位 + 风险提示）    |
| GET    | `/instances`                          | 当前用户实例列表                            |
| POST   | `/instances`                          | 创建实例；QQ 空配置自动填默认值并生成 Token |
| GET    | `/instances/{id}`                     | 实例详情                                    |
| DELETE | `/instances/{id}`                     | 删除实例                                    |
| POST   | `/instances/{id}/connect`             | 连接/启动                                   |
| POST   | `/instances/{id}/disconnect`          | 断开                                        |
| POST   | `/instances/{id}/login`               | 获取扫码/授权引导                           |
| POST   | `/instances/{id}/login/status`        | 登录状态                                    |
| GET    | `/instances/{id}/conversations`       | 会话列表                                    |
| GET    | `/instances/{id}/messages?chat_id=`   | 消息历史                                    |
| POST   | `/instances/{id}/send`                | 发送消息                                    |
| GET    | `/instances/{id}/groups`              | 群列表                                      |
| POST   | `/instances/{id}/groups/{gid}/action` | 群管理操作                                  |
| POST   | `/events/{kind}`                      | 平台事件回调（`X-Messaging-Token` 鉴权）    |

## 5. 安全与合规

- 配置（含事件 token）整体加密存储（复用 `security.encrypt_secret`），API 返回时对 token 脱敏。
- 事件回调要求实例级 token，防止伪造消息注入。
- QQ 第三方协议有封号风险：创建/启用时前端展示风险提示，文档明示合规边界。
- 默认不自动连接任何实例，必须用户显式启用。
