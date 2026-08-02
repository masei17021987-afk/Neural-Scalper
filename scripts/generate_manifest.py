#!/usr/bin/env python3
"""Generate FILE_MANIFEST_SHA256.txt for distributable source files."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "FILE_MANIFEST_SHA256.txt"
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


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if path == OUTPUT or any(part in IGNORE_PARTS for part in rel.parts):
        return False
    if any(root == rel.parent or root in rel.parents for root in RUNTIME_ROOTS):
        return path.name == ".gitkeep"
    return path.is_file()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    version = "unknown"
    version_file = ROOT / "VERSION.txt"
    if version_file.exists():
        for line in version_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("Version:"):
                version = line.split(":", 1)[1].strip()
                break

    files = sorted(path for path in ROOT.rglob("*") if included(path))
    lines = [
        "# CryptoHunter Neural Scalper file manifest",
        f"# Version: {version}",
        "# FILE_MANIFEST_SHA256.txt intentionally excludes itself.",
        "",
    ]
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        lines.append(f"{sha256(path)}  {rel}")
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Manifest written: {len(files)} files")


if __name__ == "__main__":
    main()
