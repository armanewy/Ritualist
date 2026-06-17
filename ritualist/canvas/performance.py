from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

CANVAS_PERFORMANCE_SCHEMA_VERSION = "ritualist.canvas.performance.v1"


class CanvasPerformanceMode(StrEnum):
    LOW = "low"
    BALANCED = "balanced"
    HIGH = "high"


@dataclass(frozen=True)
class CanvasPerformanceSettings:
    mode: CanvasPerformanceMode = CanvasPerformanceMode.BALANCED
    animations: bool = True
    blur: bool = False
    shadows: str = "simple"
    image_resolution_cap: int = 1440
    live_update_rate_hz: int = 30
    max_animated_components: int = 48
    show_performance_overlay: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": CANVAS_PERFORMANCE_SCHEMA_VERSION,
            "mode": self.mode.value,
            "animations": self.animations,
            "blur": self.blur,
            "shadows": self.shadows,
            "image_resolution_cap": self.image_resolution_cap,
            "live_update_rate_hz": self.live_update_rate_hz,
            "max_animated_components": self.max_animated_components,
            "show_performance_overlay": self.show_performance_overlay,
        }


def performance_settings_for_mode(
    mode: str | CanvasPerformanceMode,
    *,
    show_performance_overlay: bool = False,
) -> CanvasPerformanceSettings:
    resolved = _normalize_mode(mode)
    if resolved is CanvasPerformanceMode.LOW:
        return CanvasPerformanceSettings(
            mode=resolved,
            animations=False,
            blur=False,
            shadows="none",
            image_resolution_cap=720,
            live_update_rate_hz=15,
            max_animated_components=0,
            show_performance_overlay=show_performance_overlay,
        )
    if resolved is CanvasPerformanceMode.HIGH:
        return CanvasPerformanceSettings(
            mode=resolved,
            animations=True,
            blur=False,
            shadows="rich",
            image_resolution_cap=2160,
            live_update_rate_hz=60,
            max_animated_components=96,
            show_performance_overlay=show_performance_overlay,
        )
    return CanvasPerformanceSettings(
        mode=CanvasPerformanceMode.BALANCED,
        animations=True,
        blur=False,
        shadows="simple",
        image_resolution_cap=1440,
        live_update_rate_hz=30,
        max_animated_components=48,
        show_performance_overlay=show_performance_overlay,
    )


def _normalize_mode(mode: str | CanvasPerformanceMode) -> CanvasPerformanceMode:
    try:
        return CanvasPerformanceMode(str(mode).strip().casefold())
    except ValueError:
        return CanvasPerformanceMode.BALANCED
