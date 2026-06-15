from __future__ import annotations

import pytest

from ritualist.adapters.shell import ShellAdapter, resolve_local_command_path
from ritualist.errors import RitualistError


def test_launch_missing_local_path_raises_friendly_error(tmp_path):
    missing = tmp_path / "missing.exe"

    with pytest.raises(RitualistError) as exc:
        ShellAdapter().launch(command=str(missing))

    assert "app.launch command path does not exist" in str(exc.value)
    assert str(missing) in str(exc.value)
    assert "Edit the recipe variable or config" in str(exc.value)


def test_resolve_local_command_path_ignores_urls_and_shell_targets():
    assert resolve_local_command_path("https://example.test") is None
    assert resolve_local_command_path("shell:AppsFolder\\Example") is None
