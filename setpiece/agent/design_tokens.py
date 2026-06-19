from __future__ import annotations

from types import MappingProxyType
from typing import Final, Mapping

TokenValue = int | str

QUIET_INSTRUMENT_CONTRACT_ID: Final = "setpiece.agent.quiet_instrument.v1"
BASE_THEME_ID: Final = "setpiece.paper"

_TOKENS: Final[dict[str, TokenValue]] = {
    "contract.id": QUIET_INSTRUMENT_CONTRACT_ID,
    "base.theme": BASE_THEME_ID,
    "font.family.primary": "Segoe UI Variable",
    "font.family.fallback": "Segoe UI",
    "font.size.minimum_epx": 12,
    "font.size.body_epx": 13,
    "font.size.caption_epx": 12,
    "font.size.title_epx": 18,
    "font.case": "sentence",
    "color.canvas": "#F7F4EE",
    "color.shell": "#FFFFFF",
    "color.panel": "#FFFFFF",
    "color.panel_alt": "#DDE7E8",
    "color.panel_muted": "#DDE7E8",
    "color.text": "#22272B",
    "color.text_muted": "#687278",
    "color.border": "#DDE7E8",
    "color.border_strong": "#70777C",
    "color.focus_ring": "#3C6F82",
    "color.accent": "#3C6F82",
    "color.on_accent": "#FFFFFF",
    "color.semantic.running": "#3C6F82",
    "color.semantic.running_panel": "#DDE7E8",
    "color.semantic.waiting": "#A36B25",
    "color.semantic.waiting_panel": "#F7F4EE",
    "color.semantic.confirmation": "#6E5A8A",
    "color.semantic.confirmation_panel": "#DDE7E8",
    "color.semantic.failure": "#A84942",
    "color.semantic.failure_panel": "#F7F4EE",
    "color.semantic.recovery": "#45715F",
    "color.semantic.recovery_panel": "#DDE7E8",
    "color.shadow.outer": "#26000000",
    "geometry.base_epx": 4,
    "geometry.space.xs_epx": 4,
    "geometry.space.sm_epx": 8,
    "geometry.space.md_epx": 12,
    "geometry.space.lg_epx": 16,
    "geometry.space.xl_epx": 24,
    "geometry.space.xxl_epx": 32,
    "geometry.radius.outer_epx": 10,
    "geometry.radius.control_epx": 6,
    "geometry.hit_target.primary_epx": 40,
    "geometry.shadow.outer.blur_epx": 24,
    "geometry.shadow.outer.y_epx": 10,
    "motion.flyout.min_ms": 120,
    "motion.flyout.max_ms": 160,
    "motion.flyout.default_ms": 140,
    "motion.state.min_ms": 180,
    "motion.state.max_ms": 220,
    "motion.state.default_ms": 200,
    "motion.reduced.default_ms": 0,
    "motion.reduced.fade_ms": 60,
    "opacity.disabled": 56,
}

QUIET_INSTRUMENT_TOKENS: Final[Mapping[str, TokenValue]] = MappingProxyType(_TOKENS)


def quiet_instrument_tokens() -> Mapping[str, TokenValue]:
    return QUIET_INSTRUMENT_TOKENS


def token(name: str, default: TokenValue | None = None) -> TokenValue:
    try:
        return QUIET_INSTRUMENT_TOKENS[name]
    except KeyError:
        if default is not None:
            return default
        raise
