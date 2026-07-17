---
name: hx-init
description: 为当前项目配置 AI Coding 强约束。使用前扫描仓库并按用户环境定制方案，支持 Python/React、改造模式和初始化模式。用于 hx-init、工程强约束、Claude/Codex hooks、Git commit message hook、GitHub Actions workflow、ruff/biome/lefthook/pre-commit 配置。
---

# hx-init

你是 AI, 在当前工作目录配置强约束套件。目标是"适配这个项目", 不是复制模板。

## 不可跳过的原则

- 先扫描再修改。由 `hx-skill-orchestrator` 调度或用户明确要求安装、初始化、接入时，视为已授权项目内可回滚修改，不再要求选择模式或严格度。
- 优先复用现有工具链、脚本、版本、包管理器和 CI; 只补缺口。
- 已存在文件先读懂再最小 patch; 无法安全合并时跳过并说明。
- `.agents/` 下新增文件可以纯新增; 工程配置文件必须审阅式修改。
- hooks 不得把全量告警灌进上下文; 只输出摘要和日志路径。
- 所有 `.sh` 写盘后 `chmod 755`。

## 流程

### 1. 读取必要参考

始终读 `references/_shared/README.md`。扫描后按需读:

- Python: `references/python/README.md`
- React/Web: `references/react/README.md`

### 2. 自动扫描

先收集事实, 不要先下结论:

- Git: 当前分支、`git status --short`、是否已有未提交改动。
- 项目类型: `pyproject.toml`/`requirements*.txt`/`setup.cfg`/`.py`, `package.json`/`tsconfig.json`/锁文件。
- 源码边界: `src/`, `app/`, `packages/*`, `apps/*`, `server/`, `client/`, tests 目录, monorepo workspace。
- 现有工具: ruff/black/isort/mypy/pyright/ty/pytest/tox/nox/pre-commit; eslint/biome/prettier/tsc/knip/lefthook/husky/lint-staged; vitest/jest/playwright/cypress。
- 包管理器: uv/poetry/pdm/pip, npm/pnpm/yarn/bun, 从锁文件和脚本判断。
- 规模风险: 文件数、明显生成目录、是否可能出现 10w+ 历史告警。
- Agent 配置: `.claude/`, `.codex/`, `.agents/` 是否已存在; 不再生成根目录 `CLAUDE.md` / `AGENTS.md`。
- CI 配置: `.github/workflows/` 是否存在, 是否已有 lint/test/verify workflow。

可用命令示例: `git status --short --branch`, `rg --files`, `find . -maxdepth 3`, `python --version`, `node --version`, `uv --version`, `jq '.scripts' package.json`。不要在完成扫描前跑全量 lint/typecheck。

### 3. 自动形成并执行方案

根据扫描事实形成内部执行清单:

- 检测结果: 语言、源码目录、包管理器、已有质量工具、风险点。
- 自动模式: 已有业务代码使用 `modify`; 空仓库或仅有脚手架使用 `init`; 用户明确约束时使用 custom。
- 将新增/修改/跳过的文件列表。
- 将运行的安装命令和验证命令。
- 将新增/合并/跳过的 GitHub Actions workflow。
- 将复用的测试入口，以及 static/S1/S2/S3 的覆盖范围；真实外部 canary 单独列为 S4。
- 严格度: 老项目自动使用 changed-files/baseline，新项目自动使用 strict。
- Git commit message hook 默认不启用，只有用户明确要求时安装。

若用户只要求审视或提案则不写盘。明确要求安装、初始化、接入或由调度器调用时直接执行；仅在凭证、不可逆操作、业务方向冲突或无法保护用户改动时询问。

### 4. 模式

**modify (自动)**: 在现有项目上补 hooks/rules。只对缺失配置做最小 patch，不强行启用会产生大量历史告警的规则。

**init (自动)**: 仓库缺少有效业务代码，或用户明确要求初始化时使用。

1. 检查 Git；不是 Git 仓库时可初始化，但不自动提交或推送。
2. 工作区已有改动时记录并保护这些路径，不 stage、不覆盖；只有直接冲突时询问。
3. 安装并运行必要验证，自行修复本次引入的问题。
4. 汇报告警摘要和日志路径，不自动修完整历史债。

**custom**: 用户选定语言、工具或严格度时, 尊重用户选择; 若会破坏现有流程, 先指出风险再执行。

### 5. 安装规则

- 禁止创建软链接安装配置。不得使用 `ln -s`、符号链接、硬链接或链接式复制来安装 `.agents/`、`.claude/`、`.codex/` 下的文件。
- `.agents/`、`.claude/`、`.codex/` 下需要的规则、hooks、JSON 配置必须写成真实实体文件。已有文件必须先读取, 再由 AI 审阅式手动补充缺失内容; 不覆盖、不整文件替换、不用软链绕过合并。
- 不生成根目录 `CLAUDE.md` / `AGENTS.md`; 规则入口和 hooks 入口按目标 agent 分别落到对应目录的实体文件中。若同一内容需要给 Claude 和 Codex 复用, 分别写入 `.claude/` 和 `.codex/` 的真实文件, 并在 manifest 记录来源和差异。
- GitHub Actions workflow 是 hx-init 的标准安装项: 没有 workflow 时按语言模板新增 `.github/workflows/ci.yml`; 已有 workflow 时审阅式合并 verify/lint/test 步骤或跳过, 不整文件替换。
- Git commit-msg hook 默认不安装；只有用户已经明确要求该规则时才写 `.git/hooks/commit-msg`，已有非 hx-init hook 时默认跳过。
- Python 和 React 同时存在时, 合并 hook 列表: PostToolUse 可连续执行清理和对应 formatter; Stop hook 调用一个适配后的 verify 脚本或多个语言 verify。
- 写 `.agents/.install-manifest.json`, 至少记录 `mode`, `created`, `modified`, `skipped`, `commands`, `logs`。
- 配置文件不要整文件替换。优先使用结构化编辑; TOML/YAML/JSON 无可靠解析器时, 做清晰的局部 patch 并展示 diff。
- 安装依赖前从锁文件和现有脚本确认包管理器；不要在 pnpm/yarn/bun 项目里使用 npm。

### 6. 告警和日志策略

- Stop hooks 必须把完整输出写入 `.git/hx-init/logs` 或用户 cache, 不污染工作区。
- 注入给 AI 的内容只允许是摘要: 检查项、失败数量估计、前 3-5 条样例、日志路径、查看命令。
- 面对 10w+ 告警, 先归类和抽样, 不要粘贴全量输出。
- 需要查详情时, 使用 `sed -n`, `rg`, `head`, `tail` 针对日志文件定位; 一次读取不超过约 200 行。

### 7. 安装后

执行方案并验证。失败时优先修复本次引入的问题；历史债自动建立 baseline 或缩小到 changed-files。只有降低安全边界或改变业务行为时才询问用户。

## 扩展

加新语言: `references/` 下新建目录 -> 写参考说明和模板 -> 在本文件的扫描和安装规则中加入选择逻辑。
