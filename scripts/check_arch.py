"""架构静态检查: 行数 / 目录文件数 / _前缀越界 / 中文命名。

对应 Ruff 无原生规则或需强化的约束 (返回非0即 fail):
1. 单 .py <= 300 行
2. 目录内 .py 数量 2~5 (不含 __init__.py)
3. 公开文件 (非 impl/) 禁止 def _xxx
4. 禁止中文/非ASCII 标识符 (对付 AI 幻觉, 与 Ruff PLC2401 互补)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

MAX_LINES: int = 300
MIN_PY_PER_DIR: int = 2
MAX_PY_PER_DIR: int = 5
SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".claude",
        "scripts",
        "tests",
        "ref",
        "web",
    }
)
SKIP_FILES: frozenset[str] = frozenset({"bootstrap.py"})
CJK_RANGES: tuple[tuple[str, str], ...] = (
    ("\u4e00", "\u9fff"),  # CJK 汉字
    ("\u3400", "\u4dbf"),  # 扩展A
    ("\u3000", "\u303f"),  # CJK 标点
    ("\uff00", "\uffef"),  # 全角字符
)


def iter_py_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts) or p.name in SKIP_FILES:
            continue
        out.append(p)
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
            errs.append(f"[文件数] {d} 仅 {cnt} 个 .py < {MIN_PY_PER_DIR}, 建议合并")
        elif cnt > MAX_PY_PER_DIR:
            errs.append(f"[文件数] {d} 有 {cnt} 个 .py > {MAX_PY_PER_DIR}, 请拆分")
    return errs


def check_private_funcs(files: list[Path]) -> list[str]:
    errs: list[str] = []
    for f in files:
        if "impl" in f.parts or f.name == "__init__.py":
            continue
        for node in ast.parse(f.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
                "_"
            ):
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
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and _has_cjk(
                node.name
            ):
                errs.append(f"[中文命名] {f}:{node.lineno} {node.name} 中文标识符, 用英文")
            elif (
                isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and _has_cjk(node.id)
            ):
                errs.append(f"[中文命名] {f}:{node.lineno} 变量 {node.id} 含中文")
            elif isinstance(node, ast.arg) and _has_cjk(node.arg):
                errs.append(f"[中文命名] {f}:{node.lineno} 参数 {node.arg} 含中文")
    return errs


def main() -> int:
    root: Path = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    files: list[Path] = iter_py_files(root)
    errors: list[str] = []
    errors += check_line_count(files)
    errors += check_dir_file_count(root)
    errors += check_private_funcs(files)
    errors += check_chinese_names(files)
    if errors:
        print("FAIL 架构检查未通过:\n" + "\n".join(f"  - {e}" for e in errors))
        return 1
    print(f"PASS arch-check ({len(files)} 个文件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
