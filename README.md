<p align="center">
  <img src="web/public/icon-192.png" alt="HX-Email 图标" width="128" height="128" />
</p>

<h1 align="center">HX-Email</h1>

<p align="center">
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img alt="React 19" src="https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black" />
  <img alt="TypeScript 5.7" src="https://img.shields.io/badge/TypeScript-5.7-3178C6?style=for-the-badge&logo=typescript&logoColor=white" />
  <img alt="Tailwind CSS 3" src="https://img.shields.io/badge/Tailwind_CSS-3.4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white" />
  <img alt="shadcn/ui" src="https://img.shields.io/badge/shadcn%2Fui-latest-000000?style=for-the-badge&logo=shadcnui&logoColor=white" />
  <br />
  <img alt="Vite 5" src="https://img.shields.io/badge/Vite-5-646CFF?style=for-the-badge&logo=vite&logoColor=white" />
  <img alt="SQLite 3" src="https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white" />
  <img alt="Docker Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" />
  <img alt="Google OAuth" src="https://img.shields.io/badge/Google-OAuth-4285F4?style=for-the-badge&logo=google&logoColor=white" />
  <img alt="Microsoft OAuth" src="https://img.shields.io/badge/Microsoft-OAuth-0078D4?style=for-the-badge&logo=microsoft&logoColor=white" />
  <img alt="中英双语" src="https://img.shields.io/badge/i18n-%E4%B8%AD%E8%8B%B1%E5%8F%8C%E8%AF%AD-10B981?style=for-the-badge" />
</p>

## 项目简介

HX-Email 是一款面向「注册与验证」场景的现代化邮箱管理平台，帮助你统一管理多个邮箱账号（Microsoft Outlook、Google Gmail、任意 IMAP 邮箱），自动读取验证码与验证链接，记录每个可用邮箱在外部平台上的绑定关系，并通过邮箱池、临时邮箱与自动化通知把「注册 — 收码 — 绑定」的流程化繁为简。

项目采用 FastAPI（Python 3.12 + uv）与 React 19（TypeScript + Vite + Tailwind CSS + shadcn/ui）全栈重写，内置深色主题工作台与中英双语界面（跟随浏览器语言，默认英文、中文浏览器自动显示中文），支持 Docker 一键部署与主从同步。

## 功能特性

### 多邮箱账号统一管理

- 支持 Microsoft Outlook（OAuth / IMAP）、Google Gmail（OAuth / 应用专用密码）以及任意自定义 IMAP 邮箱账号
- 「可用邮箱」体系：主邮箱地址、别名邮箱地址、Plus 子地址（兼容读取）、临时邮箱地址统一纳管
- 分组与标签组织邮箱资源，可按分组配置轮询与通知策略

### 验证码自动读取

- 自动提取邮件中的验证码与验证链接，支持中英文等多语言上下文识别
- 按可用邮箱的收件地址精确过滤，读取别名邮箱时不会串读同账号其他地址的验证码
- 验证码命中历史记录，随时回溯

### 平台与平台绑定

- 平台目录管理，记录每个可用邮箱注册 / 登录了哪些外部平台
- 绑定状态支持「使用中 / 待验证 / 有风险 / 不可用 / 已归档」，可附加备注说明用途与限制

### 邮箱池与临时邮箱

- 邮箱池：领取 / 释放 / 完成 / 冷却的完整状态流转，配合外部 API 供自动化注册流程取号
- 外部邮箱池 API：`claim-random`、`claim-release`、`claim-complete` 与 `stats`（API Key 鉴权）
- 临时邮箱：基于 Cloudflare 的临时邮箱服务，快速创建临时地址、读信并提取验证码与验证链接，支持归档

### 邮件自动化与通知

- 全局轮询 + 分组轮询（3～86400 秒可配），新邮件首次入库才触发投递
- 通知渠道：SMTP 转发、Telegram、Webhook 回调（可携带 Bearer Token）、浏览器通知、自定义 Shell 流水线
- 投递失败进入 outbox，自动重试最多 3 次

### 消息插件（QQ / 微信 / Telegram / Discord）

- 以**插件模式**接入即时消息平台，像收邮件一样收发消息；非主功能，按需添加激活
- 首个落地：**QQ**，内置受管协议引擎（Lagrange.OneBot，加载插件时自动查询官方 Release
  下载并拉起，用户零安装），
  支持扫码登录、登录态长期维持、私聊/群聊收发、历史消息与群管理（踢人/禁言/全体禁言/退群）；
  也可通过高级设置对接外部 NapCat/Lagrange
- 统一抽象 `MessagingAdapter`：登录引导、会话、消息、发送、群组操作与能力位
  （是否支持扫码/群组/历史/风险等级），为微信（企业微信）、Telegram、Discord 预留同一套 API
- 平台事件回调 `POST /api/v1/messaging/events/{kind}` 以实例级 Token 鉴权，消息落库可查
- 详细设计与平台风险矩阵见 [`docs/messaging-plugins.md`](docs/messaging-plugins.md)

### 发信与 OAuth 令牌工具

- 使用账号关联的可用邮箱发送调试邮件（SMTP）
- OAuth 令牌工具：Microsoft 与 Google 一键授权、生成授权链接、回调换取 Token 并持久化，支持 Token 自动刷新与刷新日志
- 附带 Tampermonkey 脚本，辅助在 Azure 门户完成应用注册配置

### Google 对接

- Gmail 账号接入：OAuth 一键授权或应用专用密码
- 面向 Google OAuth 品牌验证就绪：公开首页、隐私政策、服务条款页面，后台支持上传 Google 站点验证文件

### 自动构建与发布

仓库内置 GitHub Actions 流水线（`.github/workflows/release.yml`），推送到 `v*` 标签（如 `v0.3.0`）时自动完成：

1. 运行完整验证（`bash scripts/verify.sh`）；
2. 构建并推送 `linux/amd64` 与 `linux/arm64` 双架构镜像到 GitHub Container Registry（`hx-email-server` / `hx-email-web`，打 `vX.Y.Z` 与 `latest` 两个标签）；
3. 创建 GitHub Release（自动生成变更说明）。

也可在 Actions 页面手动触发 `release` 工作流并填写版本号（如 `0.3.0`），效果相同。发布后，已有部署在「设置 → 系统状态」点击「立即更新」即可升级。

## 主从同步（双向收敛）

- 适合「VPS 主实例 + 本地从机」场景：主 → 从拉取 + 从 → 主推送，两端只增不删、按自然键去重
- 同步覆盖用户、邮箱账号、可用邮箱、分组 / 标签、平台绑定、临时邮箱、邮箱池、验证码记录、已收邮件与数据目录文件
- 周期同步（后台线程，失败不影响服务）或 CLI 手动同步：`hx-email sync`、`hx-email sync --push-only`

### 数据安全与运维

- 实例级备份 / 恢复（ZIP，含数据库、密钥与静态文件），兼容旧版数据格式的核心数据 JSON 导入导出
- 凭据字段加密存储，管理员审计日志，Token 刷新日志（含疑似失效 Token 账户提示）
- 多用户数据隔离，注册开关可配，管理员用户管理

### 现代化前端体验

- React 19 + TypeScript + Tailwind CSS + shadcn/ui，深色主题，framer-motion 动效
- 中英双语界面（跟随浏览器语言，默认英文），内置 Noto Sans SC 中文字体，中文显示无乱码
- 工作台内提供完整 REST API 接口清单页面，接口鉴权方式一目了然

## 技术栈

| 层   | 技术                                                                                                      |
| ---- | --------------------------------------------------------------------------------------------------------- |
| 后端 | Python 3.12 · FastAPI · uvicorn · SQLite · uv                                                             |
| 前端 | React 19 · TypeScript 5.7 · Vite 5 · Tailwind CSS 3 · shadcn/ui · Radix UI · framer-motion · lucide-react |
| 部署 | Docker · Docker Compose · nginx（前端静态托管与反向代理）                                                 |
| 质量 | ruff · mypy · biome · tsc · knip · Vitest · pytest · Playwright                                           |

## Docker 部署

### 前置要求

- Docker 24+ 与 Docker Compose v2（可用 `docker compose version` 验证）
- Linux 推荐 host 网络模式；macOS / Windows（Docker Desktop）请使用桥接版 compose 文件

### 第一步：获取代码

```bash
git clone https://github.com/HengXin666/HX-Email.git
cd HX-Email
```

### 第二步：编辑环境变量文件

```bash
cp .env.example .env
```

用任意文本编辑器打开 `.env`，按需修改：

| 变量                             | 说明                                                                     | 默认值         |
| -------------------------------- | ------------------------------------------------------------------------ | -------------- |
| `HX_EMAIL_ADMIN_USERNAME`        | 初始管理员用户名（仅首次建库时生效）                                     | `admin`        |
| `HX_EMAIL_ADMIN_PASSWORD`        | 初始管理员密码（生产环境务必修改）                                       | `admin`        |
| `HX_EMAIL_SECRET_KEY`            | 生产环境建议设置一长串随机值并保持不变；用于加密凭据，迁移时两端必须一致 | 空（自动生成） |
| `HX_EMAIL_DATA_DIR`              | 本地开发时数据库与静态文件目录                                           | `data`         |
| `HX_EMAIL_HTTP_PORT`             | Web 界面对外端口                                                         | `8080`         |
| `HX_EMAIL_BACKEND_PORT`          | 后端端口（host 模式下仅监听 127.0.0.1，不对外暴露）                      | `18090`        |
| `HX_EMAIL_SYNC_URL`              | 主实例地址（从机同步时填写，如 `http://vps.example.com:8080`）           | 空             |
| `HX_EMAIL_SYNC_TOKEN`            | 主实例管理员 Bearer token（登录接口返回）                                | 空             |
| `HX_EMAIL_SYNC_INTERVAL_SECONDS` | 从机同步周期（秒）；`0` 表示仅启动时同步一次                             | `300`          |
| `HX_EMAIL_UPDATE_ENABLED`        | Docker 自动更新开关（设置 → 系统状态 → 立即更新）                        | `true`         |
| `HX_EMAIL_IMAGE_TAG`             | 拉取/构建镜像使用的标签（发布镜像同时打 `vX.Y.Z` 与 `latest`）           | `latest`       |

注意事项：

- 管理员账号密码只在 SQLite 首次创建时读取；实例已存在后修改 `.env` 不会重置密码，请到「设置 → 用户管理」中修改
- Docker 部署时数据统一持久化到仓库根目录 `./data`（compose 将容器内 `/data` 挂载到该目录），与本地开发共用同一份数据
- 修改 `.env` 后需执行 `docker compose up -d` 重建容器，新配置才会生效

### 第三步：启动

Linux（推荐，host 网络模式）：

```bash
docker compose up -d --build
```

macOS / Windows（Docker Desktop 桥接模式）：

```bash
docker compose -f docker-compose.bridge.yml up -d --build
```

启动完成后浏览器打开 <http://127.0.0.1:8080>，使用初始账号 `admin` / `admin` 登录（生产环境请先修改）。

> 镜像说明：每次发布版本时，流水线会自动构建并推送 `ghcr.io/<owner>/hx-email-server` 与 `ghcr.io/<owner>/hx-email-web`（同时打 `vX.Y.Z` 与 `latest` 标签）。本地 `docker compose up -d --build` 会优先从源码构建；不带 `--build` 时若本地没有镜像则会拉取对应标签的发布镜像。

**代理填写说明**：系统中的分组代理 / Telegram 代理经常填写 `http://127.0.0.1:7890` 这类宿主机本地代理（Clash / V2Ray 等）。

- host 网络模式（Linux 默认）：容器与宿主机共享网络栈，`127.0.0.1:xxx` 直接生效
- 桥接模式（Mac / Windows）：容器内的 `127.0.0.1` 指向容器自身，请改填 `http://host.docker.internal:7890`（compose 已通过 `host-gateway` 映射）
- **私网/内网地址**：默认放行 RFC1918 私网段（`10.x` / `172.16-31.x` / `192.168.x`）与 ULA 地址，LAN 代理（如 `http://192.168.1.50:7890`）或 Docker 桥接网关 IP 可直接填写；仅拦截云元数据（`169.254.169.254`）、link-local、组播、TEST-NET 等危险保留段。若部署在公网且面向多租户，可在 `.env` 设置 `HX_EMAIL_ALLOW_PRIVATE_PROXY=false` 收紧为白名单（仅 `127.0.0.0/8`、`::1`、`host.docker.internal` 与公网地址）。

### 更新与升级

**方式一：界面一键更新（推荐）**

登录后进入「设置 → 系统状态」：

1. 点击「获取更新公告」或打开页面时自动检查，若发现新版本会显示更新提示（更新公告来自 GitHub Releases）；
2. 点击「立即更新」并确认，系统会自动拉取最新镜像并重建容器，服务短暂中断后自动恢复；
3. 更新完成后页面自动刷新，显示新的版本号。

该功能由后端通过宿主机 Docker socket 执行 `docker compose pull` + `docker compose up -d` 完成（更新容器独立于当前容器运行，重建过程中不会中断）。compose 文件默认挂载了 `/var/run/docker.sock` 与 `./:/compose` 并默认启用 `HX_EMAIL_UPDATE_ENABLED=true`。

> ⚠️ 安全提示：挂载 docker socket 等于把宿主机的 Docker 控制权交给容器内进程，仅建议在可信主机上使用。不需要该功能时，在 `.env` 设置 `HX_EMAIL_UPDATE_ENABLED=false` 并删除 compose 文件中对应的两行挂载即可。

**方式二：手动更新**

```bash
git pull
docker compose up -d --build
```

两种方式都会执行数据库迁移，原有 `./data` 数据保持不变。

### 数据持久化与迁移

- 数据（SQLite 与静态图片）持久化在仓库根目录 `./data`，包含隐藏文件（如自动生成的加密密钥 `.hx_email_secret_key`）
- 完整迁移：停止容器后拷贝整个 `./data` 目录；若设置了 `HX_EMAIL_SECRET_KEY`，目标环境必须配置相同值
- 也可在「设置 → 用户管理 → 实例备份」下载完整实例 ZIP，或上传 ZIP 恢复。恢复会替换当前数据并使所有登录失效，恢复后请使用备份中的管理员账号重新登录；该 ZIP 包含敏感凭据，请像数据库备份一样妥善保管

## 主从同步

适合「VPS 上跑主实例、本地跑从机」的场景：VPS 不稳定或跑路时，本地保留一份完整、最新的数据镜像；从机新增的账号也能同步回主实例。同步方向为**主 → 从（拉取）+ 从 → 主（推送）**，两端**只增不删**，按自然键去重，保证不重复、不丢失。

从机配置（`.env` 中的 `HX_EMAIL_SYNC_*`）：

```dotenv
HX_EMAIL_SYNC_URL=http://vps.example.com:8080   # 主实例地址
HX_EMAIL_SYNC_TOKEN=xxx                         # 主实例管理员登录 token 或主实例外部 API Key
HX_EMAIL_SYNC_INTERVAL_SECONDS=300              # 周期（秒）；0 = 仅启动时同步一次
```

- 从机启动服务后立即同步一轮（拉取 + 推送），之后按间隔周期同步（后台线程，失败不影响服务）
- 不启动服务也能手动同步：`hx-email sync`；只推送不拉取：`hx-email sync --push-only`
- 同步内容：用户、邮箱账号、可用邮箱、分组 / 标签、平台绑定、临时邮箱、邮件池、验证码记录、已收邮件，以及数据目录内的文件（按内容哈希去重）
- 主实例通过 `GET /api/v1/admin/sync/snapshot` 提供快照，可先用该接口验证主实例可达与 token 有效；从机推送走 `POST /api/v1/admin/sync/push`。这两个接口接受主实例管理员登录 token，也接受主实例配置的外部 API Key；若返回 `403 Admin required`，说明 token 有效但不是管理员会话（例如误用了外部 API Key 之外的普通用户 token）
- 从机首次同步前建议清空数据目录（保持镜像一致）；加密密钥 `.hx_email_secret_key` 仅在从机缺失时写入——若两端各自已有密钥，主实例的加密字段（如 OAuth token）将无法在从机解密，此时请在两端配置相同的 `HX_EMAIL_SECRET_KEY`

## 本地开发

前置要求：Python 3.12+（`uv`）、Node.js 24+（`npm`）。

一键启动前后端：

```bash
./scripts/dev.sh
```

默认地址：

- 后端：<http://127.0.0.1:8000>
- 前端：<http://0.0.0.0:5173>

覆盖端口：

```bash
HX_EMAIL_BACKEND_PORT=8010 HX_EMAIL_FRONTEND_PORT=5174 ./scripts/dev.sh
```

单独开发后端：

```bash
cd server
uv run hx-email migrate
uv run uvicorn hx_email.app:app --reload
```

单独开发前端：

```bash
cd web
npm install
npm run dev
```

## 验证

```bash
bash scripts/verify.sh
```

该命令会依次运行 Python 与 React 静态检查、类型检查、架构检查、死代码分析、Vitest、pytest 与 Playwright 浏览器流程（首次使用需安装 Chromium：`cd web && npx playwright install chromium`）。

## 相关文档

- [API 文档](docs/api.md) —— 全部 REST 接口与鉴权说明
- [邮件轮询与转发](docs/mail-automation.md) —— 自动化触发规则、Webhook 事件结构、Shell 流水线与外部邮箱池 API
- [Google OAuth 品牌验证](docs/google-oauth-verification.md) —— 面向 Google 审核的部署自检与配置步骤
- [设计说明](docs/rewrite-design.md) —— 领域模型与设计原则
