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

### 发信与 OAuth 令牌工具

- 使用账号关联的可用邮箱发送调试邮件（SMTP）
- OAuth 令牌工具：Microsoft 与 Google 一键授权、生成授权链接、回调换取 Token 并持久化，支持 Token 自动刷新与刷新日志
- 附带 Tampermonkey 脚本，辅助在 Azure 门户完成应用注册配置

### Google 对接

- Gmail 账号接入：OAuth 一键授权或应用专用密码
- 面向 Google OAuth 品牌验证就绪：公开首页、隐私政策、服务条款页面，后台支持上传 Google 站点验证文件

### 主从同步（双向收敛）

- 适合「VPS 主实例 + 本地从机」场景：主 → 从拉取 + 从 → 主推送，两端只增不删、按自然键去重
- 同步覆盖用户、邮箱账号、可用邮箱、分组 / 标签、平台绑定、临时邮箱、邮箱池、验证码记录、已收邮件与数据目录文件
- 周期同步（后台线程，失败不影响服务）或 CLI 手动同步：`hx-email sync`、`hx-email sync --push-only`

### 数据安全与运维

- 实例级备份 / 恢复（ZIP，含数据库、密钥与静态文件），兼容旧版的核心数据 JSON 导入导出
- 凭据字段加密存储，管理员审计日志，Token 刷新日志（含疑似失效 Token 账户提示）
- 多用户数据隔离，注册开关可配，管理员用户管理

### 现代化前端体验

- React 19 + TypeScript + Tailwind CSS + shadcn/ui，深色主题，framer-motion 动效
- 中英双语界面（跟随浏览器语言，默认英文），内置 Noto Sans SC 中文字体，中文显示无乱码
- 工作台内提供完整 REST API 接口清单页面，接口鉴权方式一目了然

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.12 · FastAPI · uvicorn · SQLite · uv |
| 前端 | React 19 · TypeScript 5.7 · Vite 5 · Tailwind CSS 3 · shadcn/ui · Radix UI · framer-motion · lucide-react |
| 部署 | Docker · Docker Compose · nginx（前端静态托管与反向代理） |
| 质量 | ruff · mypy · biome · tsc · knip · Vitest · pytest · Playwright |

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

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `HX_EMAIL_ADMIN_USERNAME` | 初始管理员用户名（仅首次建库时生效） | `admin` |
| `HX_EMAIL_ADMIN_PASSWORD` | 初始管理员密码（生产环境务必修改） | `admin` |
| `HX_EMAIL_SECRET_KEY` | 生产环境建议设置一长串随机值并保持不变；用于加密凭据，迁移时两端必须一致 | 空（自动生成） |
| `HX_EMAIL_DATA_DIR` | 本地开发时数据库与静态文件目录 | `data` |
| `HX_EMAIL_HTTP_PORT` | Web 界面对外端口 | `8080` |
| `HX_EMAIL_BACKEND_PORT` | 后端端口（host 模式下仅监听 127.0.0.1，不对外暴露） | `18090` |
| `HX_EMAIL_SYNC_URL` | 主实例地址（从机同步时填写，如 `http://vps.example.com:8080`） | 空 |
| `HX_EMAIL_SYNC_TOKEN` | 主实例管理员 Bearer token（登录接口返回） | 空 |
| `HX_EMAIL_SYNC_INTERVAL_SECONDS` | 从机同步周期（秒）；`0` 表示仅启动时同步一次 | `300` |

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

**代理填写说明**：系统中的分组代理 / Telegram 代理经常填写 `http://127.0.0.1:7890` 这类宿主机本地代理（Clash / V2Ray 等）。

- host 网络模式（Linux 默认）：容器与宿主机共享网络栈，`127.0.0.1:xxx` 直接生效
- 桥接模式（Mac / Windows）：容器内的 `127.0.0.1` 指向容器自身，请改填 `http://host.docker.internal:7890`（compose 已通过 `host-gateway` 映射）

### 更新与升级

```bash
git pull
docker compose up -d --build
```

### 数据持久化与迁移

- 数据（SQLite 与静态图片）持久化在仓库根目录 `./data`，包含隐藏文件（如自动生成的加密密钥 `.hx_email_secret_key`）
- 完整迁移：停止容器后拷贝整个 `./data` 目录；若设置了 `HX_EMAIL_SECRET_KEY`，目标环境必须配置相同值
- 也可在「设置 → 用户管理 → 实例备份」下载完整实例 ZIP，或上传 ZIP 恢复。恢复会替换当前数据并使所有登录失效，恢复后请使用备份中的管理员账号重新登录；该 ZIP 包含敏感凭据，请像数据库备份一样妥善保管

## 主从同步

适合「VPS 上跑主实例、本地跑从机」的场景：VPS 不稳定或跑路时，本地保留一份完整、最新的数据镜像；从机新增的账号也能同步回主实例。同步方向为**主 → 从（拉取）+ 从 → 主（推送）**，两端**只增不删**，按自然键去重，保证不重复、不丢失。

从机配置（`.env` 中的 `HX_EMAIL_SYNC_*`）：

```dotenv
HX_EMAIL_SYNC_URL=http://vps.example.com:8080   # 主实例地址
HX_EMAIL_SYNC_TOKEN=xxx                         # 主实例管理员 Bearer token
HX_EMAIL_SYNC_INTERVAL_SECONDS=300              # 周期（秒）；0 = 仅启动时同步一次
```

- 从机启动服务后立即同步一轮（拉取 + 推送），之后按间隔周期同步（后台线程，失败不影响服务）
- 不启动服务也能手动同步：`hx-email sync`；只推送不拉取：`hx-email sync --push-only`
- 同步内容：用户、邮箱账号、可用邮箱、分组 / 标签、平台绑定、临时邮箱、邮件池、验证码记录、已收邮件，以及数据目录内的文件（按内容哈希去重）
- 主实例通过管理员鉴权的 `GET /api/v1/admin/sync/snapshot` 提供快照，可先用该接口验证主实例可达与 token 有效；从机推送走管理员鉴权的 `POST /api/v1/admin/sync/push`
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
- [重写设计说明](docs/重写设计说明.md) —— 领域模型与设计原则
