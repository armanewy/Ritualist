from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _load_checker_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_line_endings.py"
    spec = importlib.util.spec_from_file_location("setpiece_line_endings", script)
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


def test_managed_git_head_blobs_have_github_readable_line_endings():
    if shutil.which("git") is None:
        pytest.skip("git is not available")

    checker = _load_checker_module()
    root = checker.repo_root(Path(__file__))
    paths = checker.iter_source_files(root)
    missing = [path for path in paths if checker.git_blob_stats(root, path, ref="HEAD", source="git_head") is None]
    if len(missing) == len(paths):
        pytest.skip("git HEAD blobs are not available in this checkout")

    problems = checker.collect_git_blob_problems(root, paths, ref="HEAD", source="git_head")

    assert not problems, "\n".join(problem.format(root) for problem in problems)


def test_managed_git_index_blobs_have_github_readable_line_endings():
    if shutil.which("git") is None:
        pytest.skip("git is not available")

    checker = _load_checker_module()
    root = checker.repo_root(Path(__file__))
    paths = checker.iter_source_files(root)
    missing = [path for path in paths if checker.git_index_stats(root, path) is None]
    if len(missing) == len(paths):
        pytest.skip("git index blobs are not available in this checkout")

    problems = checker.collect_git_index_problems(root, paths)

    assert not problems, "\n".join(problem.format(root) for problem in problems)


def test_watched_canvas_git_head_blobs_have_github_readable_line_endings():
    if shutil.which("git") is None:
        pytest.skip("git is not available")

    checker = _load_checker_module()
    root = checker.repo_root(Path(__file__))
    watched = [
        root / "setpiece" / "canvas" / "runtime.py",
        root / "setpiece" / "canvas" / "controller.py",
        root / "setpiece" / "canvas" / "view_model.py",
        root / "tests" / "test_canvas_runtime.py",
    ]
    missing = [path for path in watched if checker.git_blob_stats(root, path, ref="HEAD", source="git_head") is None]
    if missing:
        pytest.skip("git HEAD blobs are not available in this checkout")

    problems = checker.collect_git_blob_problems(root, watched, ref="HEAD", source="git_head")

    assert not problems, "\n".join(problem.format(root) for problem in problems)


def test_line_ending_checker_catches_cr_only_git_head_blob(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is not available")

    checker = _load_checker_module()
    path = tmp_path / "bad.py"
    path.write_bytes(b"x = 1\r" * 300)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "add", "bad.py"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=setpiece@example.test",
            "-c",
            "user.name=Setpiece Test",
            "commit",
            "-m",
            "bad blob",
        ],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    path.write_bytes(b"x = 1\n" * 300)

    problems = checker.collect_git_blob_problems(tmp_path, [path], ref="HEAD", source="git_head")

    messages = [problem.message for problem in problems]
    assert any("CR-only" in message for message in messages)
    assert any("collapsed" in message or "longest" in message for message in messages)
    assert {problem.source for problem in problems} == {"git_head"}


def test_line_ending_checker_catches_cr_only_git_index_blob(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is not available")

    checker = _load_checker_module()
    path = tmp_path / "bad.py"
    path.write_bytes(b"x = 1\n" * 300)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "add", "bad.py"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=setpiece@example.test",
            "-c",
            "user.name=Setpiece Test",
            "commit",
            "-m",
            "good blob",
        ],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    path.write_bytes(b"x = 1\r" * 300)
    subprocess.run(["git", "add", "bad.py"], cwd=tmp_path, check=True)

    problems = checker.collect_git_index_problems(tmp_path, [path])

    messages = [problem.message for problem in problems]
    assert any("CR-only" in message for message in messages)
    assert any("collapsed" in message or "longest" in message for message in messages)
    assert {problem.source for problem in problems} == {"git_index"}


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
