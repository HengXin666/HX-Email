#!/usr/bin/env python3
"""Zero-dependency repository verifier used by hx-test-pipeline."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
LINK_RE = re.compile(r"\[[^]]+\]\((?!https?://|#)([^)]+)\)")


def files(root: Path, pattern: str) -> list[Path]:
    return [path for path in root.rglob(pattern) if not SKIP_PARTS.intersection(path.parts)]


def static_checks(root: Path) -> list[str]:
    errors: list[str] = []
    for skill in sorted({*root.glob("skills/*/SKILL.md"), *root.glob(".codex/skills/*/SKILL.md")}):
        text = skill.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            errors.append(f"{skill}: missing frontmatter")
            continue
        block = text.split("---\n", 2)[1]
        name = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", block)
        description = re.search(r"(?m)^description:\s*\S", block)
        if not name or name.group(1) != skill.parent.name or not description:
            errors.append(f"{skill}: invalid name or description")
        if "TODO" in text:
            errors.append(f"{skill}: TODO remains")
        for markdown in files(skill.parent, "*.md"):
            for target in LINK_RE.findall(markdown.read_text(encoding="utf-8")):
                clean = target.split("#", 1)[0]
                if clean and not (markdown.parent / clean).resolve().exists():
                    errors.append(f"{markdown}: broken link {target}")

    for path in files(root, "*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
    for path in files(root, "*.py"):
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"{path}: invalid Python: {exc}")
    shell = files(root, "*.sh")
    if shell:
        result = subprocess.run(["bash", "-n", *map(str, shell)], capture_output=True, text=True)
        if result.returncode:
            errors.append(result.stderr.strip())
    return errors


def package_manager(root: Path) -> str:
    choices = (
        ("pnpm-lock.yaml", "pnpm"),
        ("bun.lock", "bun"),
        ("bun.lockb", "bun"),
        ("yarn.lock", "yarn"),
        ("package-lock.json", "npm"),
    )
    for marker, command in choices:
        if (root / marker).exists() and shutil.which(command):
            return command
    return "npm" if shutil.which("npm") else ""


def discovered_commands(root: Path) -> list[tuple[str, list[str], dict[str, str] | None]]:
    verify = root / "scripts/verify.sh"
    if verify.is_file():
        return [("project verify", ["bash", str(verify)], None)]

    commands: list[tuple[str, list[str], dict[str, str] | None]] = []
    installer = root / "install.sh"
    if installer.is_file():
        commands.append(("installer CLI", ["bash", str(installer), "--help"], None))
    tests = root / "tests"
    if tests.is_dir():
        if (root / "uv.lock").exists() and shutil.which("uv"):
            commands.append(("python tests", ["uv", "run", "pytest", "-q"], None))
        elif (root / "poetry.lock").exists() and shutil.which("poetry"):
            commands.append(("python tests", ["poetry", "run", "pytest", "-q"], None))
        elif (root / "pdm.lock").exists() and shutil.which("pdm"):
            commands.append(("python tests", ["pdm", "run", "pytest", "-q"], None))
        else:
            probe = subprocess.run([sys.executable, "-m", "pytest", "--version"], capture_output=True)
            if probe.returncode == 0:
                commands.append(("python tests", [sys.executable, "-m", "pytest", "-q"], None))

    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, json.JSONDecodeError):
            scripts = {}
        pm = package_manager(root)
        if pm:
            for name in ("lint", "typecheck", "type-check", "test", "build"):
                if name in scripts:
                    env = {**os.environ, "CI": "1"} if name == "test" else None
                    commands.append((f"package {name}", [pm, "run", name], env))
    return commands


def run(root: Path, strict: bool, canary: bool) -> int:
    errors = static_checks(root)
    if errors:
        for error in errors:
            print(f"FAIL static: {error}")
        return 1
    print("PASS static")

    commands = discovered_commands(root)
    if not commands:
        print("SKIP behavior tests: no existing project test entry detected")
        if strict:
            return 1
    for label, command, env in commands:
        print(f"RUN  {label}: {' '.join(command)}", flush=True)
        result = subprocess.run(command, cwd=root, env=env, check=False)
        if result.returncode:
            print(f"FAIL {label}: exit={result.returncode}")
            return result.returncode
        print(f"PASS {label}")

    if canary:
        script = root / "scripts/canary.sh"
        if not script.is_file():
            print("SKIP S4 canary: scripts/canary.sh is not configured")
            return 1 if strict else 0
        result = subprocess.run(["bash", str(script)], cwd=root, check=False)
        if result.returncode:
            print(f"FAIL S4 canary: exit={result.returncode}")
            return result.returncode
        print("PASS S4 canary")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--canary", action="store_true")
    args = parser.parse_args()
    return run(Path(args.root).resolve(), args.strict, args.canary)


if __name__ == "__main__":
    raise SystemExit(main())
