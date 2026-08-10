# <img src="web/public/icon-192.png" width="32" height="32" alt="HX-Email 图标" /> HX-Email

HX-Email 是一款自托管的多邮箱统一管理平台，采用 FastAPI + React / TypeScript
（shadcn/ui + Tailwind）构建。集中管理邮箱账号、临时邮箱与平台绑定，自动读取
验证码并按规则收发邮件，让多账号管理简单高效。

## 功能亮点

- **多账号统一管理**：一个界面集中管理 Outlook、Gmail 等邮箱账号，统一查看状态、刷新登录态与维护凭据；
- **验证码自动读取**：自动识别邮件中的验证码并高亮展示，配合浏览器脚本一键回填；
- **Google / Gmail 对接**：通过 Google OAuth 连接 Gmail 账号，支持 Gmail 别名投递与 Google 品牌验证（详见下文）；
- **平台绑定**：记录可用邮箱与外部平台的绑定关系，支持分组、标签与绑定状态管理；
- **临时邮箱**：内置临时邮箱池，按需创建、按策略回收，保护主邮箱；
- **邮件自动化**：定时拉取、SMTP 发送、转发，以及 Telegram / Webhook / 自定义脚本管道通知；
- **导入导出与备份**：管理员可一键备份、导出、导入与恢复整个实例；
- **主从同步**：双向收敛的实例级同步，支持“VPS 主实例 + 本地从机”互为镜像；
- **自托管**：数据默认只存于你自己的服务器，不依赖第三方云，隐私可控。

## Google 对接

- **Google OAuth 连接 Gmail**：在「设置 → 邮箱账号」中配置 Google OAuth（Client ID / Client Secret），通过 Google 官方授权流程连接 Gmail 账号，用于收取邮件、自动读取验证码、发送与转发邮件；
- **Gmail 别名投递**：支持 Gmail 点号（dot）别名等收件地址，验证码读取按收件地址精确匹配，不会串读同一账号下其他地址的邮件；
- **Google 品牌验证**：内置公开的首页、隐私政策与服务条款页面，并支持在「系统设置 → 基础 → Google 站点验证」上传验证文件、在站点根路径公开提供，完整验证流程见 [docs/google-oauth-verification.md](docs/google-oauth-verification.md)。

## Requirements

- Python 3.12+ with `uv`
- Node.js 24+ with npm

## Backend

```bash
cd server
uv run pytest
uv run hx-email migrate
uv run uvicorn hx_email.app:app --reload
```

The FastAPI app exposes:

- `GET /health` for health checks
- `hx-email migrate` for the initial SQLite migration entrypoint
- `GET /data/export` and `POST /data/import` for core first-phase data backup
  and migration. The payload covers email accounts, usable emails, aliases,
  groups, tags, platforms and platform bindings for the authenticated user only.

Mail automation supports settings-driven polling, per-group polling and
delivery controls, SMTP forwarding, Telegram, webhook callbacks, browser
notifications, and custom `.sh` pipelines. The event and external mailbox-pool
contracts are documented in [docs/mail-automation.md](docs/mail-automation.md).

Configuration is loaded from `.env`. Copy `.env.example` before first startup:

```bash
cp .env.example .env
```

The initial admin login defaults to:

- username: `admin`
- password: `admin`

Configure it in `.env`:

```dotenv
HX_EMAIL_ADMIN_USERNAME=your-admin
HX_EMAIL_ADMIN_PASSWORD=your-password
```

These admin credentials are used only when the SQLite database creates the
initial admin user. Changing `.env` after the database already exists does not
reset an existing admin password; use the account settings screen to change it.

The SQLite data directory defaults to `data`; configure it in `.env`:

```dotenv
HX_EMAIL_DATA_DIR=data
```

Keep the entire data directory, including hidden files, when moving an
instance. It contains the SQLite database, generated secret key, settings,
users, credentials, messages and static files. Stop the containers before
copying it so SQLite WAL state is consistent. If `HX_EMAIL_SECRET_KEY` is set,
the same value must be supplied at the destination; when it is empty, the
generated `.hx_email_secret_key` inside the data directory is sufficient.

## Frontend

```bash
cd web
npm install
npm test
npm run build
npm run dev
```

## Local Development

Start the backend and frontend together from the repository root:

```bash
./scripts/dev.sh
```

Defaults:

- backend: `http://127.0.0.1:8000`
- frontend: `http://0.0.0.0:5173`

Override ports or hosts when needed:

```bash
HX_EMAIL_BACKEND_PORT=8010 HX_EMAIL_FRONTEND_PORT=5174 ./scripts/dev.sh
```

前端使用 React + TypeScript + Tailwind（shadcn/ui）构建，默认深色主题，提供
登录/注册、总览工作台、邮箱账号、临时邮箱、平台绑定、邮件自动化与系统设置等
完整界面。

## Docker 一键部署

Linux (推荐, host 网络模式):

```bash
docker compose up -d --build
```

打开 `http://127.0.0.1:8080`,默认账号 `admin` / `admin`(生产环境请先在
`.env` 中修改 `HX_EMAIL_ADMIN_*` 与 `HX_EMAIL_SECRET_KEY`)。

**代理兼容说明**:系统中的分组代理 / Telegram 代理经常填
`http://127.0.0.1:7890` 这类宿主机本地代理(Clash / V2Ray 等)。默认
compose 使用 host 网络模式,容器与宿主机共享网络栈,这类代理填写
`127.0.0.1:xxx` 可直接生效。后端仅监听 `127.0.0.1`,只有 nginx 前端
(`HX_EMAIL_HTTP_PORT`,默认 8080)对外暴露。

Mac / Windows(Docker Desktop)使用桥接版:

```bash
docker compose -f docker-compose.bridge.yml up -d --build
```

桥接模式下容器内的 `127.0.0.1` 指向容器自身,宿主机代理请改填
`http://host.docker.internal:7890`(compose 已通过 `host-gateway` 映射)。

数据(SQLite 与静态图片)持久化在仓库根目录 `./data`,与本地开发共用同一
目录;完整迁移前停止容器并拷贝整个目录(包含隐藏文件)。端口可通过 `.env`
中的 `HX_EMAIL_HTTP_PORT` / `HX_EMAIL_BACKEND_PORT` 覆盖。

管理员也可以在“设置 → 用户管理 → 实例备份”中下载完整实例 ZIP，或上传
ZIP 恢复。恢复会替换当前数据并使所有登录失效；恢复后使用备份中的管理员
账号重新登录。该 ZIP 包含敏感凭据，应像数据库备份一样保管。

### 主从同步（双向收敛）

适合“VPS 上跑主实例、本地跑从机”的场景：VPS 不稳定或跑路时，本地保留一份
完整、最新的数据镜像；从机新增的账号也能同步回主实例。同步方向是
**主 → 从（拉取）+ 从 → 主（推送）**，两端都**只增不删**（任一方删除的数据
不会从另一方删除），按自然键去重，保证不重复、不丢失。同步的契约是
**账号不能缺失**（不含临时邮箱账号实例）：一方新增的账号会出现在另一方，
但任一方都不会单方面覆盖另一方的已有数据——推送在主节点按“仅补缺”合并，
不会改动主节点已存在的账号、分组、设置等。

从机配置（`HX_EMAIL_SYNC_*`，见 `.env.example`）：

```bash
HX_EMAIL_SYNC_URL=             # 主实例地址，例如 http://vps.example.com:8080
HX_EMAIL_SYNC_TOKEN=           # 主实例管理员账号的 Bearer token（登录接口获取）
HX_EMAIL_SYNC_INTERVAL_SECONDS=300  # 周期（秒）；0 = 仅启动时同步一次
```

- 从机启动服务后立即同步一轮（拉取 + 推送），之后按间隔周期同步
  （后台线程，失败不影响服务）；
- 不启动服务也能手动同步一轮：`hx-email sync`；只推送不同步拉取：
  `hx-email sync --push-only`（需同样配置好环境变量）；
- 同步内容：SQLite 中的用户、账号、邮箱、分组/标签、平台绑定、临时邮箱、
  邮件池、验证码记录、已收邮件，以及数据目录内的文件（按内容哈希去重）；
- 主实例通过管理员鉴权的 `GET /api/v1/admin/sync/snapshot` 提供快照，可先
  用该接口验证主实例可达与 token 有效；从机推送走管理员鉴权的
  `POST /api/v1/admin/sync/push`（`sync` 命令/周期同步自动携带本地快照）；
- 从机首次同步前建议清空数据目录（保持镜像一致）；加密密钥
  `.hx_email_secret_key` 仅在从机缺失时写入，从机已有自己的密钥则保留，
  此时主实例的加密字段（如 OAuth token）将无法在从机解密，需改用
  `HX_EMAIL_SECRET_KEY` 并在两端配置相同值。

## Whole Repo Checks

```bash
bash scripts/verify.sh
```

This single local/CI gate runs Python and React static checks, type checks,
architecture checks, dead-code analysis, Vitest, pytest, and the Playwright S3
browser flow. Install its local Chromium runtime once with:

```bash
cd web
npx playwright install chromium
```

The S3 flow starts an isolated FastAPI database and a Vite production preview,
then verifies authentication rejection, recovery, protected navigation, and
logout in Chromium. Real OAuth, Graph, IMAP, SMTP, and temporary-mail provider
canaries stay outside the PR gate.

## Migration Scope

The rewrite preserves the first-phase core data model. Import/export is scoped
to administrator-only instance backups. The legacy `/data/export` and
`/data/import` endpoints are also administrator-only and remain limited to the
core data model for compatibility. Browser extension features, closed-page
VAPID push, one-click updates and plugin-based temporary mail providers remain
deferred follow-up capabilities.
