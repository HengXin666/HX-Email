# 通用配置（所有语言共享）

以下文件对所有语言类型都生效。先扫描；用户明确要求安装/接入或由调度器调用时直接执行安全的项目内修改。

## 安装策略

- 禁止软链安装。不得使用 `ln -s`、硬链接或链接式复制来创建 `.agents/`、`.claude/`、`.codex/` 下的配置。
- 所有 agent 配置必须是实体文件。若 Claude 和 Codex 需要同一份规则或 hook, 分别写入 `.claude/` 和 `.codex/` 的真实文件; `.agents/` 可以作为安装记录和共享参考, 但不能通过软链充当目标文件。
- 已存在的真实文件不覆盖。若已有 `.claude/settings.json`、`.claude/hooks.json`、`.codex/hooks.json` 或 hook 脚本, 先读内容, 再由 AI 手动补充缺失字段、追加缺失 hook, 或跳过并说明原因。
- 不生成根目录 `CLAUDE.md` / `AGENTS.md`; 不创建任何根目录或 agent 入口软链。
- 写 `.agents/.install-manifest.json`, 记录本次 `created`, `modified`, `skipped`, `commands`, `logs`。
- GitHub Actions workflow 是标准安装项。若 `.github/workflows/` 不存在, 创建语言对应的 `ci.yml`; 若已存在 workflow, 只做审阅式合并或跳过。
- 大项目默认 baseline: hooks 只给摘要, 完整日志进 `.git/hx-init/logs` 或用户 cache。
- 兼容旧版本时, 将 `.agents/logs/` 加入 `.gitignore`, 防止历史 hook 日志污染工作区。

## hooks

| 文件                               | 目标路径                                   |
| ---------------------------------- | ------------------------------------------ |
| `hooks/strip_emoji.sh`             | `.agents/hooks/strip_emoji.sh`             |
| `hooks/clean_chars.sh`             | `.agents/hooks/clean_chars.sh`             |
| `hooks/check_commit_msg.sh`        | `.agents/hooks/check_commit_msg.sh`        |
| `hooks/install_commit_msg_hook.sh` | `.agents/hooks/install_commit_msg_hook.sh` |

## 可选 Git commit-msg hook

这个 hook 是 opt-in, 不默认安装。启用后, `git commit` 的第一行必须匹配:

```text
[type] subject
```

默认允许:

```text
feat fix docs style refactor perf test build ci chore revert release deps security
```

安装规则:

- 只有用户已经明确要求 commit message 规则时才启用；否则直接跳过，不额外提问。
- 复制 `check_commit_msg.sh` 和 `install_commit_msg_hook.sh` 到 `.agents/hooks/`。
- 运行 `bash .agents/hooks/install_commit_msg_hook.sh`。
- 若已有非 hx-init 管理的 `.git/hooks/commit-msg`, 默认跳过, 不覆盖。
- 用户明确要求替换时才运行 `bash .agents/hooks/install_commit_msg_hook.sh --force`。
- 自定义类型可设置 `HX_COMMIT_TYPES="feat fix wip"`。

失败时 hook 会阻止提交, 并提示用户用 `git commit -m "[feat] ..."` 或 `git commit --amend -m "[fix] ..."` 修正。

## 静态文件

| 文件         | 目标路径     | 模式                                 |
| ------------ | ------------ | ------------------------------------ |
| `.gitignore` | `.gitignore` | init 时审阅式合并; modify 时通常跳过 |

## Agent 实体文件（禁止软链）

这些路径如需启用, 必须创建或审阅式合并为真实文件/目录:

| 目标                    | 规则                                               |
| ----------------------- | -------------------------------------------------- |
| `.claude/settings.json` | 不存在时按项目定制后新增; 存在时手动合并缺失配置   |
| `.claude/hooks.json`    | 不存在时按项目定制后新增; 存在时手动合并缺失 hooks |
| `.claude/hooks/*.sh`    | 写真实脚本文件, 写盘后 `chmod 755`                 |
| `.claude/rules/*.md`    | 写真实规则文件, 已存在则读后补充或跳过             |
| `.codex/hooks.json`     | 不存在时按项目定制后新增; 存在时手动合并缺失 hooks |
| `.codex/hooks/*.sh`     | 写真实脚本文件, 写盘后 `chmod 755`                 |
| `.codex/rules/*.md`     | 写真实规则文件, 已存在则读后补充或跳过             |

## 执行摘要

安装前展示:

- 检测到的语言、包管理器、源码目录、已有工具。
- 将创建、将修改、将跳过的路径。
- 将执行的命令。
- hooks 的严格度和日志位置。

用户只要求审视时仅输出提案；安装、接入或调度模式直接执行。只有凭证、不可逆操作、业务方向冲突或用户改动无法保护时询问。
