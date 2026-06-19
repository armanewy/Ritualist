from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

PATTERN = re.compile(
    r"Ritualist|RITUALIST_|(?<![A-Za-z0-9_])ritualist(?![A-Za-z0-9_])|"
    r"\.ritualistpack|\.ritualistcanvas|\.ritualisttheme|\.ritualistsuite|Ritualist\.exe"
)

SCAN_SUFFIXES = {
    ".py",
    ".qml",
    ".ps1",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".txt",
    ".csv",
    ".spec",
    ".svg",
}

SKIP_PARTS = {
    ".git",
    ".tmp",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "artifacts",
}

HISTORICAL_FILES = {
    "CHANGELOG.md",
    "RELEASE_CHECKLIST.md",
    "RELEASE_NOTES.md",
}

LEGACY_COMPAT_FILES = {
    "setpiece/paths.py",
    "setpiece/packs.py",
    "setpiece/canvas_packs.py",
    "setpiece/canvas/models.py",
    "setpiece/suite_packs.py",
    "tests/test_e2e.py",
    "tests/test_setpiece_rebrand.py",
    "tests/test_packs.py",
    "tests/test_canvas_packs.py",
    "tests/test_suite_packs.py",
}

LEGACY_COMPAT_MARKERS = (
    "LEGACY_",
    "legacy",
    "Legacy",
    "RITUALIST_E2E",
    ".ritualistpack",
    ".ritualistcanvas",
    ".ritualisttheme",
    ".ritualistsuite",
    "ritualist.pack.v1",
    "ritualist.canvas_pack.v1",
    "ritualist.theme_pack.v1",
    "ritualist.suite_pack.v1",
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    text: str

    def format(self) -> str:
        rel = self.path.relative_to(ROOT).as_posix()
        return f"{rel}:{self.line}: {self.text.strip()}"


def main() -> int:
    findings = scan()
    if findings:
        for finding in findings:
            print(finding.format())
        return 1
    print("Setpiece rebrand stale-reference scan passed")
    return 0


def scan() -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel == "scripts/check_setpiece_rebrand.py":
            continue
        if any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if not PATTERN.search(line):
                continue
            if _allowed(rel, line):
                continue
            findings.append(Finding(path=path, line=line_no, text=line))
    return findings


def _allowed(rel: str, line: str) -> bool:
    if rel in HISTORICAL_FILES:
        return True
    if rel in LEGACY_COMPAT_FILES and any(marker in line for marker in LEGACY_COMPAT_MARKERS):
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
