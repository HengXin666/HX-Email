# AI Coding 强约束

## 0. 黄金工作流 (Explore -> Plan -> Code -> Commit)

1. Explore: 先只读不改, 定位+理解再动手。
2. Plan: 复杂任务先输出实现计划 (改哪些文件、为什么)。
3. Code: 按计划编码。
4. Commit: 提交前必须 `bash scripts/verify.sh` 全绿 (Stop hook 会兜底强制)。

## 1. 不可违背的硬约束

- 单 .py 文件 <= 300 行; 超出 -> 拆分或下沉 impl/。
- 所有函数/返回值/变量必须类型标注 (def f() -> int, x: int = f())。
  类型是给你(Agent)的机器可验证契约, 由 ruff(ANN) + 类型检查器双重保证。
- 一个目录下 .py 数必须 2~5 (不含 **init**.py)。
- 公开文件禁止 _ 开头函数; 私有逻辑只能放 impl/。
- 严禁中文/非ASCII 命名: 变量/函数/类/参数/文件名一律英文 (中文注释、字符串 OK)。
  若你正打算写 def 计算金额() -- 停下, 这是幻觉, 改成 def calc_amount()。
- 拒绝浅模块(碎片化小文件), 推崇深模块(简单接口 + impl 复杂内核)。

## 2. 目录分层 (强制, 依赖方向 api -> server -> models)

- api/ 按"前端页面"划分子文件夹
- server/ 按"业务"划分; impl/ 放私有实现
- models/ 按"数据表"划分
- config/const/ 所有常量按业务声明
- utils/ 所有通用方法按功能实现
  详细规则+反例见 .claude/rules/architecture.md 与 .claude/rules/naming.md。
  React TS 项目额外规则见 .claude/rules/react-architecture.md 与 .claude/rules/react-ts-naming.md。

## 3. 验证闭环

任何改动后必须通过 (返回0才算"完成", 别凭"看起来对了"就停):
bash scripts/verify.sh

---

# Agent Notes — 决策记录

非平凡改动的定义: 改变行为、架构、跨文件的契约、流程或工具、测试策略, 或任何落盘 / 线上 / 配置格式。
每一次非平凡改动都在**同一次提交里**新增或更新一篇 Agent Note; 纯机械的局部编辑豁免。

1. 改一个声明之前, 先找它旁边引用的 note —— `.agents/notes/<lifecycle>/<class>/<file>.md` 路径,
   通常写在注释或 JSDoc 里。先读它: 它记着已经否决过什么、为什么。
2. 优先更新已经拥有那条决策的 note。过时的事实**就地重写**, 不要追加变更历史;
   绝不把一篇 note 改写成另一条决策 —— 要取代它, 并双向互链。
3. 新方向从 `.agents/notes/proposed/{class}/` 开始; 落地时在同一提交里移到
   `implemented/{class}/`, 用现在时陈述, 并从它约束的代码里引用它 (见第 1 条)。
4. 每一篇 active note 都带 `## Alternatives considered`, 其中必须有"什么都不做 / 复用现有"
   这一项, 且每个被否掉的选项都要先给出它最强的理由, 再否决。
5. note 被完全取代时用 `npm run notes:archive` 归档; rejected 提案不再能拦住一个
   有人可能重犯的错误时, 直接删除。

推送前跑 `npm run verify-notes`。受保护的源码 (`server/**` `web/**` `scripts/**`)
改动若同一次改动里没有 note, 门禁会失败; 要刻意豁免, 写 `.agents/notes/NOTE-EXEMPT.md`,
内容为 `note-exempt: <为什么这次不需要 note>`。规则细节见 `.agents/notes/AGENTS.md`。
