from __future__ import annotations

import pytest

from ritualist.errors import TemplateError
from ritualist.templating import render_template_data


def test_render_template_data_supports_nested_values():
    rendered = render_template_data(
        {
            "url": "{{ media.url }}",
            "message": "Open {{ media.name }}",
            "steps": ["{{ media.name }}"],
        },
        {"media": {"url": "https://example.test", "name": "Video"}},
    )

    assert rendered == {
        "url": "https://example.test",
        "message": "Open Video",
        "steps": ["Video"],
    }


def test_unknown_template_variable_raises():
    with pytest.raises(TemplateError):
        render_template_data("{{ missing }}", {})
