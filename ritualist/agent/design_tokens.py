from __future__ import annotations

from types import MappingProxyType
from typing import Final, Mapping

TokenValue = int | str

QUIET_INSTRUMENT_CONTRACT_ID: Final = "ritualist.agent.quiet_instrument.v1"
BASE_THEME_ID: Final = "ritualist.paper"

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
    "color.canvas": "#f6f2ea",
    "color.shell": "#fbf8f2",
    "color.panel": "#ffffff",
    "color.panel_alt": "#f0ebe2",
    "color.panel_muted": "#ebe4d8",
    "color.text": "#24211c",
    "color.text_muted": "#675f53",
    "color.border": "#d8d0c3",
    "color.border_strong": "#bfb5a6",
    "color.focus_ring": "#1d5f99",
    "color.accent": "#2f6f8f",
    "color.on_accent": "#ffffff",
    "color.semantic.running": "#2f6f8f",
    "color.semantic.running_panel": "#e7f1f5",
    "color.semantic.waiting": "#8a6a1f",
    "color.semantic.waiting_panel": "#fff3d8",
    "color.semantic.confirmation": "#2f7d57",
    "color.semantic.confirmation_panel": "#eaf7ee",
    "color.semantic.failure": "#a23a3a",
    "color.semantic.failure_panel": "#fdeaea",
    "color.semantic.recovery": "#4f6f8f",
    "color.semantic.recovery_panel": "#e8f2f0",
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
