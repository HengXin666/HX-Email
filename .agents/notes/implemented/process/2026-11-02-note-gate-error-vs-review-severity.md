# Agent Note: 门禁退出码只由 error 级诊断决定

Status: implemented

Decision-ID: note-gate-error-vs-review-severity

## Code

- `.agents/skills/hx-agent-notes/scripts/redline/verify.py`

## Problem

`verify.py` 用 `ok=not issues` 计算结果, 而 issues 同时包含 severity=error 与 severity=review 两级诊断
全量检查时 72 项存量目录的 unowned-directory 属于 review 级, 却和 12 项真正的错误一起把退出码压成 1
结果是门禁能跑但必挡, 任何提交都无法通过, 使用者也分不清哪些是必须修的错误, 哪些只是待审核项
同一时期 CI 工作流仍调用已搬走的 `scripts/verify-all.ts`, `redline/run.ts` 被直接执行时静默退出 0, pre-commit 模板指向不存在的 `scripts/redlines/agent_notes.py`, 门禁的几个入口都不可信

## Decision

退出码只由 severity=error 决定: 存在 error 时退出 1, 只有 review 时退出 0, 工具或配置错误仍退出 2
`--json` 输出结构不变, issues 一条不少, 下游仍可按 review 出报告
终端输出照常打印全部 review 项, 最后一行分开写出两类数量, 例如 `Agent Notes: 通过 (72 项待审核, 0 项错误)` 或 `Agent Notes: 需处理, 12 项错误, 72 项待审核`
同时让所有入口指向同一个真实门禁: CI 改为调用 `cli/verify-all.ts`, `redline/run.ts` 作为入口执行时调用 runGate 并透出退出码, pre-commit 模板与 lefthook 使用同一条 `node .agents/skills/hx-agent-notes/scripts/cli/verify-all.ts --staged`

## Alternatives considered

什么都不做, 复用现有行为: 最强的理由是 review 也代表需要人看的风险, 让它挡住提交可以逼迫团队尽快为存量目录补齐决策记录, 而且不改代码就没有引入新缺陷的风险
否决原因: 72 项存量 review 让门禁对每次提交都失败, 结果只会是大家绕过或关闭门禁, 真正的 error 反而失去约束力; review 的处理渠道是报告与人工审核, 不是阻断
删除或降级 unowned-directory 检查让门禁变绿: 否决, 这会丢掉存量目录的覆盖信息, 也违反不为变绿而删规则的约束
新增 `--strict` 之类的开关让 review 可选地阻断: 否决, 目前没有需要该行为的调用方, 多一个开关只会让 CI, lefthook 与本地入口的口径再次分叉

## Consequences

只有 review 项的提交与 PR 会通过门禁, review 项仍出现在终端输出与 JSON 诊断里, 需要靠报告和人工审核跟进
notes-contract.md 中 "1 违规或待 review" 的退出码描述与新行为不一致, 需要负责该文件的人同步更新
`.agents/notes.config.json` 的 guarded 只精确纳入 `.agents/skills/hx-agent-notes/scripts/redline/verify.py` 这一个文件, 让本记录的 Code 指向真实承载者, 锚点放在 `main` 的 docstring
没有纳入整个 `.agents/skills`: 该目录里另有十余处锚点指向本仓库不存在的旧决策记录, 整目录纳入会新增同等数量的 note-path 错误, 需要先为这些脚本补齐或迁移决策记录再扩大范围
同批修复 ast-parse 误报: tree-sitter-typescript 0.23.2 的 tsx 语法只把 & 当作完整字符引用的开头, JSX 文本或 JSX 属性字符串里的裸 & 会变成 ERROR 节点, 而 tsc 接受这种写法
`anchors.py` 只对 tsx 处理这一种 ERROR: 父节点是 jsx_element, 或父节点是挂在 jsx_attribute 下的 string, 且首个子节点是 & 时, 把该字节换成空格后重新解析, 字节偏移不变, 重新解析仍有任何 ERROR 就照旧报 ast-parse 错误
