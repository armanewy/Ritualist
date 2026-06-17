from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_checker_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_line_endings.py"
    spec = importlib.util.spec_from_file_location("ritualist_line_endings", script)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_canvas_source_files_have_github_readable_line_endings():
    checker = _load_checker_module()
    root = checker.repo_root(Path(__file__))
    paths = checker.iter_source_files(root)
    problems = checker.collect_problems(root, paths)
    assert not problems, "\n".join(problem.format(root) for problem in problems)


def test_line_ending_checker_catches_cr_only_large_source(tmp_path):
    checker = _load_checker_module()
    path = tmp_path / "bad.py"
    path.write_bytes(b"x = 1\r" * 300)

    problems = checker.collect_problems(tmp_path, [path])

    messages = [problem.message for problem in problems]
    assert any("CR-only" in message for message in messages)
    assert any("collapsed" in message or "longest" in message for message in messages)


def test_line_ending_normalizer_converts_cr_only_to_lf(tmp_path):
    checker = _load_checker_module()
    path = tmp_path / "source.py"
    path.write_bytes(b"def f():\r    return 1\r")

    changed = checker.normalize_file(path)

    assert changed is True
    assert path.read_bytes() == b"def f():\n    return 1\n"


def test_line_ending_normalizer_keeps_powershell_crlf(tmp_path):
    checker = _load_checker_module()
    path = tmp_path / "build.ps1"
    path.write_bytes(b"Write-Host 'hello'\rWrite-Host 'done'\r")

    changed = checker.normalize_file(path)

    assert changed is True
    assert path.read_bytes() == b"Write-Host 'hello'\r\nWrite-Host 'done'\r\n"
