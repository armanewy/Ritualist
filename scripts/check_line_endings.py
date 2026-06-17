"""Check and optionally normalize Ritualist source line endings.

This script intentionally performs byte-level checks. Python's text helpers such
as ``splitlines()`` can make CR-only files look normal on Windows while GitHub
raw/diffs render them as a single giant line. The Canvas source files are part
of the product's core UI layer, so they must remain readable in public diffs and
tracebacks.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


MAX_LINE_LENGTH = 1_000
MIN_LINES_FOR_LARGE_FILE = 20
LARGE_FILE_BYTES = 2_048


SOURCE_PATTERNS: tuple[str, ...] = (
    ".gitattributes",
    "pyproject.toml",
    "ritualist/canvas/**/*.py",
    "ritualist/canvas/**/*.qml",
    "ritualist/canvas/**/*.yaml",
    "ritualist/canvas/**/*.yml",
    "ritualist/sample_canvases/**/*.yaml",
    "ritualist/sample_canvases/**/*.yml",
    "tests/test_canvas*.py",
    "tests/test_line_endings.py",
    "docs/canvas.md",
    "docs/roadmap.md",
    "README.md",
    "scripts/*.py",
    "scripts/*.ps1",
    ".github/workflows/*.yml",
)


EXCLUDED_PARTS: tuple[str, ...] = (
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
)


LF_EXTENSIONS = {
    ".py",
    ".qml",
    ".yaml",
    ".yml",
    ".md",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".txt",
}


CRLF_EXTENSIONS = {".ps1", ".bat", ".cmd"}

LF_FILENAMES = {".gitattributes"}


@dataclass(frozen=True)
class LineEndingStats:
    path: Path
    source: str
    size_bytes: int
    lf_count: int
    cr_count: int
    crlf_count: int
    cr_only_count: int
    longest_lf_line: int

    @property
    def line_count(self) -> int:
        # GitHub/raw viewers care about LF-delimited lines. A file with CR-only
        # separators has one LF-delimited line, even if text APIs split it.
        return self.lf_count + 1 if self.size_bytes else 0


@dataclass(frozen=True)
class LineEndingProblem:
    path: Path
    message: str
    source: str = "working_tree"

    def format(self, root: Path) -> str:
        try:
            display = self.path.relative_to(root)
        except ValueError:
            display = self.path
        return f"{display} [{self.source}]: {self.message}"


def repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "ritualist").exists():
            return candidate
    raise RuntimeError("Could not find Ritualist repository root")


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def iter_source_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in SOURCE_PATTERNS:
        for path in root.glob(pattern):
            if path.is_file() and not _is_excluded(path.relative_to(root)):
                files.add(path)
    return sorted(files)


def stats_for_bytes(path: Path, data: bytes, *, source: str) -> LineEndingStats:
    crlf_count = data.count(b"\r\n")
    cr_count = data.count(b"\r")
    lf_count = data.count(b"\n")
    cr_only_count = cr_count - crlf_count
    longest = max((len(line) for line in data.split(b"\n")), default=0)
    return LineEndingStats(
        path=path,
        source=source,
        size_bytes=len(data),
        lf_count=lf_count,
        cr_count=cr_count,
        crlf_count=crlf_count,
        cr_only_count=cr_only_count,
        longest_lf_line=longest,
    )


def stats_for(path: Path) -> LineEndingStats:
    return stats_for_bytes(path, path.read_bytes(), source="working_tree")


def _problems_for_stats(stat: LineEndingStats) -> list[LineEndingProblem]:
    problems: list[LineEndingProblem] = []
    suffix = stat.path.suffix.lower()

    if stat.cr_only_count:
        problems.append(
            LineEndingProblem(
                stat.path,
                f"contains {stat.cr_only_count} CR-only line separator(s); use LF or CRLF",
                source=stat.source,
            )
        )

    if (suffix in LF_EXTENSIONS or stat.path.name in LF_FILENAMES) and stat.crlf_count:
        problems.append(
            LineEndingProblem(
                stat.path,
                f"contains {stat.crlf_count} CRLF line ending(s); expected LF in repository",
                source=stat.source,
            )
        )

    if stat.size_bytes > LARGE_FILE_BYTES and stat.lf_count < MIN_LINES_FOR_LARGE_FILE:
        problems.append(
            LineEndingProblem(
                stat.path,
                (
                    f"has only {stat.lf_count} LF byte(s) despite {stat.size_bytes} bytes; "
                    "likely collapsed/minified source"
                ),
                source=stat.source,
            )
        )

    if stat.longest_lf_line > MAX_LINE_LENGTH:
        problems.append(
            LineEndingProblem(
                stat.path,
                f"longest LF-delimited line is {stat.longest_lf_line} bytes; max is {MAX_LINE_LENGTH}",
                source=stat.source,
            )
        )

    return problems


def collect_problems(root: Path, paths: Iterable[Path] | None = None) -> list[LineEndingProblem]:
    problems: list[LineEndingProblem] = []
    for path in paths or iter_source_files(root):
        problems.extend(_problems_for_stats(stats_for(path)))
    return problems


def _repo_relative_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    return relative.as_posix()


def _git_blob(root: Path, spec: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "show", spec],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def git_blob_stats(root: Path, path: Path, *, ref: str, source: str) -> LineEndingStats | None:
    blob = _git_blob(root, f"{ref}:{_repo_relative_path(root, path)}")
    if blob is None:
        return None
    return stats_for_bytes(path, blob, source=source)


def git_index_stats(root: Path, path: Path) -> LineEndingStats | None:
    blob = _git_blob(root, f":{_repo_relative_path(root, path)}")
    if blob is None:
        return None
    return stats_for_bytes(path, blob, source="git_index")


def collect_git_blob_problems(
    root: Path,
    paths: Iterable[Path],
    *,
    ref: str = "HEAD",
    source: str = "git_head",
) -> list[LineEndingProblem]:
    problems: list[LineEndingProblem] = []
    missing = 0
    path_list = list(paths)
    for path in path_list:
        stat = git_blob_stats(root, path, ref=ref, source=source)
        if stat is None:
            missing += 1
            continue
        problems.extend(_problems_for_stats(stat))
    if missing == len(path_list):
        print(f"Warning: no Git blobs were available for {ref}; skipped {source} checks.", file=sys.stderr)
    return problems


def collect_git_index_problems(root: Path, paths: Iterable[Path]) -> list[LineEndingProblem]:
    problems: list[LineEndingProblem] = []
    missing = 0
    path_list = list(paths)
    for path in path_list:
        stat = git_index_stats(root, path)
        if stat is None:
            missing += 1
            continue
        problems.extend(_problems_for_stats(stat))
    if missing == len(path_list):
        print("Warning: no Git index blobs were available; skipped git_index checks.", file=sys.stderr)
    return problems


def normalize_bytes(data: bytes, *, newline: bytes) -> bytes:
    # Convert all known newline variants to LF first, then emit requested style.
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if normalized and not normalized.endswith(b"\n"):
        normalized += b"\n"
    if newline == b"\n":
        return normalized
    return normalized.replace(b"\n", newline)


def desired_newline(path: Path) -> bytes:
    suffix = path.suffix.lower()
    if suffix in CRLF_EXTENSIONS:
        return b"\r\n"
    return b"\n"


def normalize_file(path: Path) -> bool:
    original = path.read_bytes()
    normalized = normalize_bytes(original, newline=desired_newline(path))
    if normalized == original:
        return False
    path.write_bytes(normalized)
    return True


def normalize_files(root: Path, paths: Iterable[Path] | None = None) -> list[Path]:
    changed: list[Path] = []
    for path in paths or iter_source_files(root):
        if normalize_file(path):
            changed.append(path)
    return changed


def _print_one_stat(root: Path, stat: LineEndingStats) -> None:
    display = stat.path.relative_to(root)
    print(
        f"{display} [{stat.source}]: size={stat.size_bytes} lf={stat.lf_count} "
        f"cr={stat.cr_count} crlf={stat.crlf_count} cr_only={stat.cr_only_count} "
        f"lines={stat.line_count} longest={stat.longest_lf_line}"
    )


def print_stats(root: Path, paths: Sequence[Path], *, check_git_head: bool, check_git_index: bool) -> None:
    for path in paths:
        for stat in _stats_for_requested_sources(
            root,
            path,
            check_git_head=check_git_head,
            check_git_index=check_git_index,
        ):
            _print_one_stat(root, stat)


def _stats_for_requested_sources(
    root: Path,
    path: Path,
    *,
    check_git_head: bool,
    check_git_index: bool,
) -> list[LineEndingStats]:
    stats = [stats_for(path)]
    if check_git_head:
        head_stat = git_blob_stats(root, path, ref="HEAD", source="git_head")
        if head_stat is not None:
            stats.append(head_stat)
    if check_git_index:
        index_stat = git_index_stats(root, path)
        if index_stat is not None:
            stats.append(index_stat)
    return stats


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="normalize managed source files in place")
    parser.add_argument("--check-git-head", action="store_true", help="also validate tracked Git HEAD blobs")
    parser.add_argument("--check-git-index", action="store_true", help="also validate staged/index Git blobs")
    parser.add_argument("--stats", action="store_true", help="print byte-level line-ending stats")
    args = parser.parse_args(argv)

    root = repo_root()
    paths = iter_source_files(root)

    if args.fix:
        changed = normalize_files(root, paths)
        if changed:
            print("Normalized line endings:")
            for path in changed:
                print(f"  {path.relative_to(root)}")
        else:
            print("Line endings already normalized.")

    if args.stats:
        print_stats(
            root,
            paths,
            check_git_head=args.check_git_head,
            check_git_index=args.check_git_index,
        )

    problems = collect_problems(root, paths)
    if args.check_git_head:
        problems.extend(collect_git_blob_problems(root, paths, ref="HEAD", source="git_head"))
    if args.check_git_index:
        problems.extend(collect_git_index_problems(root, paths))
    if problems:
        print("Line-ending/source-shape problems found:")
        for problem in problems:
            print(f"  - {problem.format(root)}")
        print("Run: python scripts/check_line_endings.py --fix")
        return 1

    print(f"Line-ending/source-shape check passed for {len(paths)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
