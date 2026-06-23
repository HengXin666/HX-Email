# AGENTS.md

> AI Agent 理解与修改本仓库的唯一入口。保持精简(右海拔):
> 只放"必须时刻在场"的强约束; 细节按需读 `.claude/rules/*`。
> 注: 本仓库已配置 Codex Hooks (.codex/hooks.json),
>     编辑后自动格式化, 收尾前自动全量校验, 无需你手动记得跑 lint。

## 0. 黄金工作流 (Explore -> Plan -> Code -> Commit)
1. Explore: 先只读不改, 定位+理解再动手。
2. Plan: 复杂任务先输出实现计划 (改哪些文件、为什么)。
3. Code: 按计划编码。
4. Commit: 提交前必须 `bash scripts/verify.sh` 全绿 (Stop hook 会兜底强制)。

## 1. 不可违背的硬约束
- 单 .py 文件 <= 300 行; 超出 -> 拆分或下沉 impl/。
- 所有函数/返回值/变量必须类型标注 (def f() -> int, x: int = f())。
  类型是给你(Agent)的机器可验证契约, 由 ruff(ANN) + 类型检查器双重保证。
- 一个目录下 .py 数必须 2~5 (不含 __init__.py)。
- 公开文件禁止 _ 开头函数; 私有逻辑只能放 impl/。
- 严禁中文/非ASCII 命名: 变量/函数/类/参数/文件名一律英文 (中文注释、字符串 OK)。
  若你正打算写 def 计算金额() -- 停下, 这是幻觉, 改成 def calc_amount()。
- 拒绝浅模块(碎片化小文件), 推崇深模块(简单接口 + impl 复杂内核)。

## 2. 目录分层 (强制, 依赖方向 api -> server -> models)
- api/           按"前端页面"划分子文件夹
- server/        按"业务"划分; impl/ 放私有实现
- models/        按"数据表"划分
- config/const/  所有常量按业务声明
- utils/         所有通用方法按功能实现
详细规则+反例见 .claude/rules/architecture.md 与 .claude/rules/naming.md。

## 3. 验证闭环
任何改动后必须通过 (返回0才算"完成", 别凭"看起来对了"就停):
    bash scripts/verify.sh
