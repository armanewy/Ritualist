from __future__ import annotations

import pytest
from pydantic import ValidationError

from ritualist.models import InputHotkeyStep


def test_input_hotkey_rejects_empty_keys_after_normalization() -> None:
    with pytest.raises(ValidationError, match="at least one non-empty key"):
        InputHotkeyStep.model_validate({"action": "input.hotkey", "keys": [" ", "\t"]})

