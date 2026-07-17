# Web 前端配置(npm/Next/Vite/React 通用)

## 核心原则: 扫描优先, 审阅安装

所有配置文件采用审阅式安装, 不直接覆盖:

1. 先 `Read` 目标项目已有配置文件(package.json, lefthook.yml, biome.json, tsconfig.json)
2. 分析已有内容
3. 决定操作: **新增文件** / **添加 section** / **修改字段** / **跳过**
4. 绝不做 `ln -s` 链接配置文件

## 扫描清单

- 包管理器: `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb`/`bun.lock`, `package-lock.json`, workspace 配置。
- 框架: Next/Vite/Remix/Astro/CRA, `src/`/`app/`/`pages/`/`packages/*`/`apps/*`。
- 现有工具: ESLint, Biome, Prettier, TypeScript, Knip, lefthook, husky, lint-staged。
- `package.json` scripts: `lint`, `format`, `typecheck`, `test`, `build`。
- 规模和历史债: TS/JS 文件数、生成目录、是否已有大量 lint/typecheck 告警。

适配优先级:

1. 已有脚本优先: hook 调用 `package.json` 里稳定存在的脚本。
2. 已有 formatter/linter 优先: ESLint/Prettier 项目不要强行换 Biome; Biome 项目不要再新增重复 ESLint 门禁。
3. 包管理器一致: pnpm 项目用 `pnpm exec`/`pnpm add -D`, yarn 项目用 `yarn`, bun 项目用 `bun`/`bunx`, npm 项目才用 `npm`/`npx`。
4. 大项目默认 baseline: Stop hook 给摘要和日志, 不要求一次修完整历史债。

## 模式

- **init**: 新分支提交初始化配置。可新增 GitHub Actions workflow/lefthook/hook/rules/deps 建议, 但已有配置仍需审阅式 patch。
- **modify**: 默认模式。优先复用已有 hooks 和规则；确有缺口时直接做安全的项目内最小补充。

## 工具链(三层门禁)

| 层级           | 工具             | 触发时机                |
| -------------- | ---------------- | ----------------------- |
| AI 实时        | biome(单文件)    | PostToolUse: Write/Edit |
| git pre-commit | biome + prettier | lefthook pre-commit     |
| git pre-push   | tsc + knip       | lefthook pre-push       |

如果项目已有 ESLint/Prettier/Husky/lint-staged, 这张表只是候选方案, 不是强制替换。

## 模板文件

| 文件                    | 目标                                                                                                        | 方式                                                           |
| ----------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `lefthook.yml`          | `lefthook.yml`                                                                                              | 审阅: 不存在则按包管理器渲染模板; 存在则对比差异、提示合并     |
| `ci.yml`                | `.github/workflows/ci.yml`                                                                                  | 审阅: 不存在则按包管理器渲染模板; 存在则只追加缺失 verify 步骤 |
| `hooks.json`            | `.claude/settings.json` / `.claude/hooks.json` 的实体配置                                                   | 不存在时新增; 存在时手动合并或跳过                             |
| `hooks-codex.json`      | `.codex/hooks.json` 的实体配置                                                                              | 不存在时新增; 存在时手动合并或跳过                             |
| `hooks/format_react.sh` | `.claude/hooks/format_react.sh`、`.codex/hooks/format_react.sh` 等需要启用的 agent 目录实体文件             | 不存在时新增                                                   |
| `hooks/verify_react.sh` | `.claude/hooks/verify_react.sh`、`.codex/hooks/verify_react.sh` 等需要启用的 agent 目录实体文件             | 不存在时新增                                                   |
| `rules/architecture.md` | `.claude/rules/react-architecture.md`、`.codex/rules/react-architecture.md` 等需要启用的 agent 目录实体文件 | 不存在时新增; 存在时跳过                                       |
| `rules/naming.md`       | `.claude/rules/react-ts-naming.md`、`.codex/rules/react-ts-naming.md` 等需要启用的 agent 目录实体文件       | 不存在时新增; 存在时跳过                                       |

`format_react.sh` 只处理本次工具写入的 JS/TS/JSON/CSS/Markdown 文件。`verify_react.sh` 运行 lint、typecheck、knip 和已存在的 `test` script；设置 `HX_VERIFY_BUILD=1` 时再运行 `build`。它只输出摘要，完整日志写入 `.git/hx-init/logs/react-verify-latest.log` 或用户 cache。

## lefthook.yml 审阅规则

模板中的 `{{PKG_EXEC}}` 必须按包管理器替换:

- npm: `npx --no-install`
- pnpm: `pnpm exec`
- yarn: `yarn exec`
- bun: `bunx`

读已有 `lefthook.yml`, 检查是否已有 `pre-commit` / `pre-push`:

- **不存在** -> init 模式写入模板；modify 模式仅在项目缺少等价 Git hook 时新增
- **存在但无前端格式化** -> 按现有工具追加 biome 或 prettier/eslint 段
- **存在且已有等价命令** -> 跳过, 不重复
- **存在 pre-push** -> 避免重复；大项目仅在现有基线可接受时追加 typecheck，默认不强加 knip

## GitHub Actions workflow

模板中的 `{{NODE_CACHE_LINE}}` / `{{INSTALL_CMD}}` / `{{VERIFY_CMD}}` 必须按包管理器和项目已有 scripts 替换:

- npm: `npm ci`, `npm run verify` 或已有 `lint`/`typecheck`/`test` 组合
- pnpm: `pnpm install --frozen-lockfile`, `pnpm run verify` 或已有脚本组合
- yarn: `yarn install --frozen-lockfile`, `yarn verify` 或已有脚本组合
- bun: `bun install --frozen-lockfile`, `bun run verify` 或已有脚本组合
- `{{NODE_CACHE_LINE}}`: npm/pnpm/yarn 渲染为 `cache: "npm"` / `cache: "pnpm"` / `cache: "yarn"`; bun 删除该行。

读已有 workflow, 检查是否已覆盖 install + lint/typecheck/test/build:

- **不存在 workflow** -> init 模式写入模板；modify 模式在仓库使用 GitHub 且缺少等价 CI 时新增
- **存在但无前端验证** -> 审阅式追加一个 job 或步骤
- **存在且已有等价命令** -> 跳过, 不重复

## 依赖安装

审阅 `package.json` 的 devDependencies 后再建议安装。命令按包管理器选择:

```bash
# npm
npm install --save-dev @biomejs/biome prettier lefthook typescript knip

# pnpm
pnpm add -D @biomejs/biome prettier lefthook typescript knip

# yarn
yarn add -D @biomejs/biome prettier lefthook typescript knip

# bun
bun add -d @biomejs/biome prettier lefthook typescript knip
```

只安装缺失依赖。若项目已有 ESLint/Prettier 或已有 Biome, 不重复安装同类工具。

验证失败时不要粘贴完整输出。查看详情:

```bash
sed -n '1,160p' "$(git rev-parse --git-path hx-init/logs)/react-verify-latest.log"
rg -n "error|failed|warning|unused" "$(git rev-parse --git-path hx-init/logs)/react-verify-latest.log" | head -80
```
