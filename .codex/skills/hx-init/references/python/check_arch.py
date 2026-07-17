"""架构静态检查: 行数 / 目录文件数 / _前缀越界 / 中文命名。

对应 Ruff 无原生规则或需强化的约束:
1. 单 .py <= 300 行
2. 目录内 .py 数量 2~5 (不含 __init__.py)
3. 公开文件 (非 impl/) 禁止 def _xxx
4. 禁止中文/非ASCII 标识符 (对付 AI 幻觉, 与 Ruff PLC2401 互补)

默认 advisory: 输出摘要但返回 0。显式传 --strict 才返回非 0。
用法: python check_arch.py [--strict] [--max-output N] <root_dir> [root_dir ...]
"""

from __future__ import annotations

import ast
import argparse
import sys
from pathlib import Path

MAX_LINES: int = 300
MIN_PY_PER_DIR: int = 2
MAX_PY_PER_DIR: int = 5
DEFAULT_MAX_OUTPUT: int = 80
SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".claude",
        ".codex",
        ".agents",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "scripts",
        "tests",
        "dist",
        "ref",
    }
)
SKIP_FILES: frozenset[str] = frozenset({"bootstrap.py", "mimimi.py"})
CJK_RANGES: tuple[tuple[str, str], ...] = (
    ("一", "鿿"),  # CJK 汉字
    ("㐀", "䶿"),  # 扩展A
    ("　", "〿"),  # CJK 标点
    ("＀", "￯"),  # 全角字符
)


def _is_skip_file(p: Path) -> bool:
    """检查是否应该跳过该文件."""
    if p.name in SKIP_FILES:
        return True
    # 跳过备份文件 (*.bak_*, *.bak, *~)
    if ".bak" in p.name or p.name.endswith("~"):
        return True
    # 跳过 skip-dirs 中的目录
    return any(part in SKIP_DIRS for part in p.parts)


def iter_py_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if _is_skip_file(p):
            continue
        out.append(p.resolve())
    return out


def _has_cjk(name: str) -> bool:
    return any(any(s <= ch <= e for s, e in CJK_RANGES) for ch in name)


def check_line_count(files: list[Path]) -> list[str]:
    errs: list[str] = []
    for f in files:
        n: int = len(f.read_text(encoding="utf-8").splitlines())
        if n > MAX_LINES:
            errs.append(f"[行数] {f} 共 {n} 行 > {MAX_LINES}, 请拆分或下沉 impl/")
    return errs


def check_dir_file_count(root: Path) -> list[str]:
    errs: list[str] = []
    counter: dict[Path, int] = {}
    for f in iter_py_files(root):
        if f.name == "__init__.py":
            continue
        counter[f.parent] = counter.get(f.parent, 0) + 1
    for d, cnt in counter.items():
        if 0 < cnt < MIN_PY_PER_DIR:
            errs.append(f"[文件数] {d.resolve()} 仅 {cnt} 个 .py < {MIN_PY_PER_DIR}, 建议合并")
        elif cnt > MAX_PY_PER_DIR:
            errs.append(f"[文件数] {d.resolve()} 有 {cnt} 个 .py > {MAX_PY_PER_DIR}, 请拆分")
    return errs


def check_private_funcs(files: list[Path]) -> list[str]:
    errs: list[str] = []
    for f in files:
        if "impl" in f.parts or f.name == "__init__.py":
            continue
        for node in ast.parse(f.read_text(encoding="utf-8")).body:
            is_fn = isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            if is_fn and node.name.startswith("_"):
                errs.append(
                    f"[私有越界] {f}:{node.lineno} def {node.name} "
                    f"公开文件禁止 _ 前缀, 请移入 impl/"
                )
    return errs


def check_chinese_names(files: list[Path]) -> list[str]:
    errs: list[str] = []
    for f in files:
        if _has_cjk(f.stem):
            errs.append(f"[中文命名] 文件名 {f.name} 含中文, 疑似 AI 幻觉, 改英文")
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            named = isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            if named and _has_cjk(node.name):
                errs.append(f"[中文命名] {f}:{node.lineno} {node.name} 中文标识符, 用英文")
            elif (
                isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and _has_cjk(node.id)
            ):
                errs.append(f"[中文命名] {f}:{node.lineno} 变量 {node.id} 含中文")
            elif isinstance(node, ast.arg) and _has_cjk(node.arg):
                errs.append(f"[中文命名] {f}:{node.lineno} 参数 {node.arg} 含中文")
    return errs


def main() -> int:
    parser = argparse.ArgumentParser(description="Architecture advisory/strict checker")
    parser.add_argument("--strict", action="store_true", help="return non-zero when violations exist")
    parser.add_argument("--max-output", type=int, default=DEFAULT_MAX_OUTPUT, help="max findings to print")
    parser.add_argument("root_dir", nargs="+")
    args = parser.parse_args()

    targets: list[Path] = [Path(a).resolve() for a in args.root_dir]
    files: list[Path] = []
    for t in targets:
        if not t.is_dir():
            print(f"WARN 目标目录不存在, 跳过: {t}", file=sys.stderr)
            continue
        files += iter_py_files(t)

    errors: list[str] = []
    errors += check_line_count(files)
    for t in targets:
        if t.is_dir():
            errors += check_dir_file_count(t)
    errors += check_private_funcs(files)
    errors += check_chinese_names(files)

    scanned_dirs: str = ", ".join(str(t) for t in targets)
    if errors:
        shown = errors[: max(args.max_output, 0)]
        omitted = len(errors) - len(shown)
        mode = "FAIL" if args.strict else "WARN"
        print(
            f"{mode} 架构检查发现 {len(errors)} 个问题 (扫描: {scanned_dirs}, "
            f"mode={'strict' if args.strict else 'advisory'}):\n"
            + "\n".join(f"  - {e}" for e in shown)
        )
        if omitted > 0:
            print(f"  ... 省略 {omitted} 个问题; 使用 --max-output 调整输出上限")
        return 1 if args.strict else 0
    print(f"PASS arch-check ({len(files)} 个文件, 扫描: {scanned_dirs})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
