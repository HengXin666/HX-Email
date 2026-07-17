# 命名与类型规则 (按需加载)

## 类型标注

- OK: def parse(raw: str) -> dict[str, int]: ...
- OK: count: int = len(items)
- NG: def parse(raw): ...
- 新项目 strict 可用 ruff ANN + 类型检查器(mypy --strict 或 ty)。
- 既有项目默认只要求本次新增/修改代码补齐类型, 不追历史债。
- 为什么强: 类型 = 给 Agent 的契约, 幻觉/错误调用在 check 阶段即暴露 (类似 js->ts)。

## 中文命名 (双重拦截)

- Ruff PLC2401 + scripts/check_arch.py 可拦中文标识符。
- 允许: 中文注释、中文字符串字面量。禁止: 中文变量/函数/类/参数/文件名。

## 私有命名

- 新项目 strict: _ 前缀仅允许在 _/impl/_.py。
- 既有项目: 不新增公开 `_` API; 历史代码先 advisory。

## 常量 / 通用方法

- 魔法值 -> config/const/<业务>.py 全大写。
- 跨业务纯函数 -> utils/<功能>.py。

## 数据库表

- 库表名称集中在一个文件定义字符串枚举, 并且封装一个基于枚举打开数据库的接口.
- 禁止写裸的数据库表名, 如 `db.open("user_table")` 是绝对禁止的. 因为没有事先定义
