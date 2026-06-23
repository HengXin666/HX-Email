# 命名与类型规则 (按需加载)

## 类型标注 (强制)
- OK: def parse(raw: str) -> dict[str, int]: ...
- OK: count: int = len(items)
- NG: def parse(raw): ...
- 强制手段: ruff ANN 规则 + 类型检查器(mypy --strict 或 ty)。
- 为什么强: 类型 = 给 Agent 的契约, 幻觉/错误调用在 check 阶段即暴露 (类似 js->ts)。

## 中文命名 (双重拦截)
- Ruff PLC2401 + scripts/check_arch.py 拦中文标识符。
- 允许: 中文注释、中文字符串字面量。禁止: 中文变量/函数/类/参数/文件名。

## 私有命名
- _ 前缀仅允许在 */impl/*.py。

## 常量 / 通用方法
- 魔法值 -> config/const/<业务>.py 全大写。
- 跨业务纯函数 -> utils/<功能>.py。
