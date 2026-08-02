#!/usr/bin/env python3
"""Fail-closed checks before publishing the project to GitHub."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_SIZE = 90 * 1024 * 1024
IGNORE_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
RUNTIME_ROOTS = {
    Path("var/data"),
    Path("var/logs"),
    Path("var/models"),
    Path("var/reports"),
    Path("var/cache"),
}
ALLOWED_RUNTIME_FILES = {".gitkeep"}
FORBIDDEN_NAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "service-account.json",
}
FORBIDDEN_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}
SECRET_PATTERNS = {
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Assigned API secret": re.compile(
        r"(?i)\b(?:api[_-]?key|api[_-]?secret|secret[_-]?key|binance[_-]?key)\b"
        r"\s*[:=]\s*['\"]([A-Za-z0-9_\-]{20,})['\"]"
    ),
}
SKIP_SECRET_SCAN = {
    Path("scripts/prepublish_check.py"),
    Path("docs/SECURITY_AND_LIMITATIONS_RU.md"),
}


def is_runtime_file(rel: Path) -> bool:
    return any(root == rel.parent or root in rel.parents for root in RUNTIME_ROOTS)


def is_internal_file(rel: Path) -> bool:
    return any(part in IGNORE_PARTS for part in rel.parts)


def staged_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]


def source_paths() -> list[Path]:
    paths: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if is_internal_file(rel) or is_runtime_file(rel):
            continue
        paths.append(rel)
    return paths


def inspect(paths: list[Path], *, staged: bool) -> list[str]:
    errors: list[str] = []
    for rel in paths:
        path = ROOT / rel
        if staged and is_runtime_file(rel) and path.name not in ALLOWED_RUNTIME_FILES:
            errors.append(f"runtime-файл попал в Git index: {rel}")
        lower_name = rel.name.lower()
        if (
            lower_name in FORBIDDEN_NAMES
            or lower_name.startswith(".env.")
            or rel.suffix.lower() in FORBIDDEN_SUFFIXES
        ):
            errors.append(f"потенциальный секретный файл: {rel}")
        if not path.exists():
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            errors.append(f"не удалось прочитать метаданные {rel}: {exc}")
            continue
        if size > MAX_FILE_SIZE:
            errors.append(f"файл больше 90 МиБ: {rel} ({size / 1024**2:.1f} МиБ)")
        if rel in SKIP_SECRET_SCAN or size > 5 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{label} обнаружен в файле: {rel}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--staged",
        action="store_true",
        help="проверить файлы, находящиеся в Git index",
    )
    args = parser.parse_args()

    try:
        paths = staged_paths() if args.staged else source_paths()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Не удалось получить список Git-файлов: {exc}", file=sys.stderr)
        return 2

    errors = inspect(paths, staged=args.staged)
    if errors:
        scope = "Git index" if args.staged else "исходные файлы"
        print(f"Публикация остановлена: проверка ({scope}) нашла риск.", file=sys.stderr)
        for item in sorted(set(errors)):
            print(f"  - {item}", file=sys.stderr)
        return 1

    scope = "Git index" if args.staged else "исходные файлы"
    print(f"Предпубликационная проверка ({scope}): рисков не обнаружено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
