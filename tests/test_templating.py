from __future__ import annotations

import pytest

from setpiece.errors import TemplateError
from setpiece.templating import render_template_data


def test_render_template_data_supports_nested_values():
    rendered = render_template_data(
        {
            "url": "{{ media.url }}",
            "path": "${ media.path }",
            "message": "Open {{ media.name }}",
            "steps": ["{{ media.name }}", "${media.name}"],
        },
        {"media": {"url": "https://example.test", "name": "Video", "path": "C:/demo"}},
    )

    assert rendered == {
        "url": "https://example.test",
        "path": "C:/demo",
        "message": "Open Video",
        "steps": ["Video", "Video"],
    }


def test_unknown_template_variable_raises():
    with pytest.raises(TemplateError):
        render_template_data("{{ missing }}", {})
