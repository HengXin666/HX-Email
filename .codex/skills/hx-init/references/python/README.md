# Python 配置

Python 安装必须适配现有工程。先扫描, 再决定要新增、局部 patch 还是跳过。

## 扫描清单

读取这些事实:

- 包管理器: `uv.lock`, `poetry.lock`, `pdm.lock`, `requirements*.txt`, `pyproject.toml`, `setup.cfg`, `tox.ini`, `noxfile.py`。
- Python 版本: `.python-version`, `pyproject.toml` 的 `requires-python`, CI 配置, 当前 `python --version`。
- 源码目录: `src/`, 顶层包目录、`app/`, `server/`, `tests/`; monorepo 中只配置用户选定范围。
- 现有质量工具: ruff/black/isort, mypy/pyright/ty, pytest, pre-commit, tox/nox。
- 规模: `.py` 文件数和明显生成目录; 大项目默认 baseline, 不一次启用会爆出海量历史告警的规则。

## 模式

- **init**: 新分支提交初始化配置。可新增缺失的 pyproject/pre-commit/GitHub Actions workflow/hooks/rules, 但已有文件仍需审阅式 patch。
- **modify**: 默认模式。优先 hooks + rules + 必要 verify; 不强行改 `pyproject.toml` 或 CI。

## 适配规则

- 已有 `pyproject.toml`: 不整文件替换。只补缺失的 `[tool.ruff]`, `[tool.mypy]` 或 `[tool.ty]` 片段; 保留项目原本依赖、line-length、exclude 和插件。
- 已有 ruff/black/isort: 复用现有 formatter/linter。不要同时引入互相冲突的 formatter。
- 已有 mypy/pyright/ty: 默认沿用现有类型检查器；没有时新项目使用稳定默认项，老项目可先跳过 typecheck 或只跑 changed-files。
- 已有 pre-commit: 追加缺失 hook，不重排已有 repo。没有时 init 模式可新增；modify 模式只在确有价值且不会重复现有 hook 时新增。
- 已有 tox/nox/pytest: `scripts/verify.sh` 应调用现有验证入口, 不臆造测试命令。
- 没有 uv 的项目不要强制 uv。按现有包管理器给命令: uv/poetry/pdm/pip 各自适配。
- `check_arch.py` 默认 advisory 且限制输出；新项目 strict 时才加 `--strict` 阻断。

## hooks

| 文件                 | 目标路径                                                                                  |
| -------------------- | ----------------------------------------------------------------------------------------- |
| `hooks/format_py.sh` | `.claude/hooks/format_py.sh`、`.codex/hooks/format_py.sh` 等需要启用的 agent 目录实体文件 |
| `hooks/verify_py.sh` | `.claude/hooks/verify_py.sh`、`.codex/hooks/verify_py.sh` 等需要启用的 agent 目录实体文件 |
| `hooks.json`         | `.claude/settings.json` / `.claude/hooks.json` 的实体配置, 存在时手动合并                 |
| `hooks-codex.json`   | `.codex/hooks.json` 的实体配置, 存在时手动合并                                            |

`format_py.sh` 只格式化本次工具写入的 Python 文件。`verify_py.sh` 运行验证后只输出摘要, 完整日志写入 `.git/hx-init/logs/python-verify-latest.log` 或用户 cache。

## 动态模板(init 模式, 替换 `{{}}` 后写入)

| 文件                     | 目标                       | 占位符                                                                                         |
| ------------------------ | -------------------------- | ---------------------------------------------------------------------------------------------- |
| `pyproject.toml`         | `pyproject.toml`           | `{{PY_VER}}` `{{RUFF_TARGET}}` `{{CHECKER_DEP_ENTRY}}` `{{CHECKER_SECTION}}` `{{TEST_IGNORE}}` |
| `pre-commit-config.yaml` | `.pre-commit-config.yaml`  | `{{CHECKER}}` `{{TYPE_CMD_PRECOMMIT}}` `{{PYTHON_RUN}}` `{{SRC_DIR}}`                          |
| `verify.sh`              | `scripts/verify.sh`        | `{{CHECKER}}` `{{TYPE_CMD_VERIFY}}` `{{TEST_CMD_VERIFY}}` `{{SRC_DIR}}`                        |
| `ci.yml`                 | `.github/workflows/ci.yml` | `{{PY_VER}}` `{{INSTALL_CMD}}` `{{VERIFY_CMD}}`                                                |

### 占位符替换规则

- `{{PY_VER}}` → `3.11`
- `{{RUFF_TARGET}}` → `py311`(PY_VER 去点)
- `{{CHECKER}}` → `mypy` / `ty` / `none`
- `{{CHECKER_DEP_ENTRY}}` → `"mypy>=1.14.1", ` / `"ty>=0.0.1a1", ` / 空字符串。该值代表可选列表项并包含尾随逗号和空格。
- `{{SRC_DIR}}` → `src` 或 `.`
- `{{TEST_IGNORE}}` → `.` 时 `"tests/**" = ["ANN", "S101"]`, 否则 `"**/tests/**" = ["ANN", "S101"]`
- `{{TYPE_CMD_PRECOMMIT}}` -> 按包管理器渲染，如 `uv run mypy .` / `poetry run mypy .` / `python -m mypy .`；checker 为 none 时渲染为 `true`
- `{{TYPE_CMD_VERIFY}}` -> 按包管理器渲染；`SRC_DIR` 不是 `.` 时在子目录内执行；checker 为 none 时渲染为 `echo "SKIP type-check: no checker selected"`
- `{{TEST_CMD_VERIFY}}` -> 优先复用现有 tox/nox/pytest 命令；没有测试入口时渲染为 `echo "SKIP tests: no test command detected"`
- `{{PYTHON_RUN}}` -> `uv run python` / `poetry run python` / `pdm run python` / `python3`
- `{{CHECKER_SECTION}}`: mypy → `[tool.mypy]` 段, ty → `[tool.ty.src]` 段, none → 空
- `{{INSTALL_CMD}}` -> 根据锁文件安装所选包管理器后执行 `uv sync` / `poetry install` / `pdm install`；pip 项目只使用项目虚拟环境，不做全局安装
- `{{VERIFY_CMD}}` -> 调用项目统一验证入口，默认 `bash scripts/verify.sh`

## 静态文件

| 文件                    | 目标                                                                                            | 模式                |
| ----------------------- | ----------------------------------------------------------------------------------------------- | ------------------- |
| `check_arch.py`         | `scripts/check_arch.py`                                                                         | 始终; 默认 advisory |
| `rules/architecture.md` | `.claude/rules/architecture.md`、`.codex/rules/architecture.md` 等需要启用的 agent 目录实体文件 | 始终                |
| `rules/naming.md`       | `.claude/rules/naming.md`、`.codex/rules/naming.md` 等需要启用的 agent 目录实体文件             | 始终                |

## GitHub Actions workflow

- 没有 `.github/workflows/*.yml` 时, 使用 `ci.yml` 渲染 `.github/workflows/ci.yml`。
- 已有 workflow 时, 先读取并判断是否已经运行 lint/test/verify; 已覆盖则跳过。
- 需要合并时只追加缺失的 verify 步骤, 不整文件替换。
- 非 GitHub 项目或用户明确不要 CI 时跳过, 并写入 manifest 的 `skipped`。

## 安装后

安装命令必须按扫描结果选择:

- uv: `uv sync`, `uv run pre-commit install`
- poetry: `poetry install`, `poetry run pre-commit install`
- pdm: `pdm install`, `pdm run pre-commit install`
- pip/venv: 自动使用项目虚拟环境；环境不存在时创建本地 `.venv`，不做全局安装

验证失败时不要粘贴完整输出。查看详情:

```bash
sed -n '1,160p' "$(git rev-parse --git-path hx-init/logs)/python-verify-latest.log"
rg -n "error|failed|Traceback|warning" "$(git rev-parse --git-path hx-init/logs)/python-verify-latest.log" | head -80
```
