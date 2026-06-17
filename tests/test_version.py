from __future__ import annotations

import tomllib
from pathlib import Path

import ritualist
from ritualist.diagnostics import collect_diagnostics


def test_project_version_matches_package_version_and_diagnostics():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_version = pyproject["project"]["version"]
    diagnostics = {item.name: item.value for item in collect_diagnostics()}

    assert project_version == "0.2.0-alpha.1"
    assert ritualist.__version__ == project_version
    assert diagnostics["App version"] == project_version
