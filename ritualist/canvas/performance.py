from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .models import (
    CanvasComponent,
    CanvasDocument,
    CanvasPerformanceClass,
    CanvasUpdateBehavior,
)
from .registry import create_component_registry

CANVAS_PERFORMANCE_SCHEMA_VERSION = "ritualist.canvas.performance.v1"
CANVAS_PERFORMANCE_DIAGNOSTICS_SCHEMA_VERSION = "ritualist.canvas.performance_diagnostics.v1"


class CanvasPerformanceMode(StrEnum):
    LOW = "low"
    BALANCED = "balanced"
    HIGH = "high"


class CanvasComponentUpdateRate(StrEnum):
    STATIC = "static"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CanvasComponentEstimatedCost(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_MIN_INTERVAL_BY_UPDATE_RATE = {
    CanvasComponentUpdateRate.LOW: 1000,
    CanvasComponentUpdateRate.MEDIUM: 250,
    CanvasComponentUpdateRate.HIGH: 50,
}


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
            "low_resource_mode": self.mode is CanvasPerformanceMode.LOW,
        }


@dataclass(frozen=True)
class CanvasComponentPerformanceProfile:
    component_type: str
    update_rate: CanvasComponentUpdateRate | str = CanvasComponentUpdateRate.STATIC
    uses_images: bool = False
    uses_animation: bool = False
    estimated_cost: CanvasComponentEstimatedCost | str = CanvasComponentEstimatedCost.LOW
    max_update_interval_ms: int | None = None

    def __post_init__(self) -> None:
        update_rate = CanvasComponentUpdateRate(str(self.update_rate))
        estimated_cost = CanvasComponentEstimatedCost(str(self.estimated_cost))
        if self.max_update_interval_ms is not None:
            if self.max_update_interval_ms <= 0:
                raise ValueError("max_update_interval_ms must be positive")
            minimum = _MIN_INTERVAL_BY_UPDATE_RATE.get(update_rate)
            if minimum is not None and self.max_update_interval_ms < minimum:
                raise ValueError(
                    f"{self.component_type}: component updates faster than declared {update_rate.value} policy"
                )
        object.__setattr__(self, "update_rate", update_rate)
        object.__setattr__(self, "estimated_cost", estimated_cost)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_type": self.component_type,
            "update_rate": self.update_rate.value,
            "uses_images": self.uses_images,
            "uses_animation": self.uses_animation,
            "estimated_cost": self.estimated_cost.value,
            "max_update_interval_ms": self.max_update_interval_ms,
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


def canvas_performance_diagnostics(
    document: CanvasDocument,
    *,
    settings: CanvasPerformanceSettings | None = None,
) -> dict[str, Any]:
    resolved_settings = settings or CanvasPerformanceSettings()
    registry = create_component_registry()
    profiles: list[CanvasComponentPerformanceProfile] = []
    warnings: list[str] = []
    missing_types: list[str] = []
    policy_violations: list[str] = []

    for component in document.components:
        try:
            spec = registry.get(component.type)
        except KeyError:
            missing_types.append(component.type)
            continue
        try:
            profiles.append(component_performance_profile(component, spec))
        except ValueError as exc:
            policy_violations.append(str(exc))

    profile_rows = [profile.to_dict() for profile in profiles]
    live_widgets = sum(
        profile.update_rate in {CanvasComponentUpdateRate.LOW, CanvasComponentUpdateRate.MEDIUM, CanvasComponentUpdateRate.HIGH}
        for profile in profiles
    )
    animated_total = sum(profile.uses_animation for profile in profiles)
    animated_components = min(animated_total, resolved_settings.max_animated_components)
    image_components = sum(profile.uses_images for profile in profiles)
    large_images = sum(_is_large_image(component, resolved_settings) for component in document.components)
    missing_cached_thumbnails = sum(
        component.type == "image" and not str(component.props_dict().get("thumbnail_cache_key") or "").strip()
        for component in document.components
    )
    high_cost_components = sum(profile.estimated_cost is CanvasComponentEstimatedCost.HIGH for profile in profiles)
    medium_cost_components = sum(profile.estimated_cost is CanvasComponentEstimatedCost.MEDIUM for profile in profiles)

    if live_widgets > 80:
        warnings.append(f"performance: {live_widgets} live widgets exceeds advisory budget 80")
    animated_warning_threshold = max(resolved_settings.max_animated_components * 2, 96)
    if animated_total > animated_warning_threshold:
        warnings.append(
            f"performance: {animated_total} animated components exceeds advisory budget "
            f"{animated_warning_threshold}"
        )
    if large_images:
        warnings.append(f"performance: {large_images} image component(s) exceed the image resolution cap")
    if missing_cached_thumbnails > 24:
        warnings.append(
            f"performance: {missing_cached_thumbnails} image component(s) are missing cached thumbnail keys"
        )
    warnings.extend(policy_violations)

    estimated_cost = _estimate_canvas_cost(
        live_widgets=live_widgets,
        animated_total=animated_total,
        image_components=image_components,
        high_cost_components=high_cost_components,
        medium_cost_components=medium_cost_components,
    )
    if estimated_cost is CanvasComponentEstimatedCost.HIGH:
        warnings.append("performance: canvas visual profile is high cost")

    summary = {
        "schema_version": CANVAS_PERFORMANCE_DIAGNOSTICS_SCHEMA_VERSION,
        "canvas_id": document.id,
        "component_count": len(document.components),
        "live_widgets": live_widgets,
        "animated_components": animated_components,
        "animated_component_total": animated_total,
        "image_components": image_components,
        "large_images": large_images,
        "missing_cached_thumbnails": missing_cached_thumbnails,
        "estimated_cost": estimated_cost.value,
        "warnings": list(dict.fromkeys(warnings)),
        "warning_count": len(dict.fromkeys(warnings)),
        "missing_component_types": sorted(set(missing_types)),
        "policy_violations": policy_violations,
        "settings": resolved_settings.to_dict(),
        "component_profiles": _profile_summary(profile_rows),
    }
    return summary


def component_performance_profile(
    component: CanvasComponent,
    spec: Any,
) -> CanvasComponentPerformanceProfile:
    props = component.props_dict()
    update_rate = _update_rate_for_behavior(spec.update_behavior)
    uses_images = component.type == "image" or bool(props.get("image") or props.get("path") or props.get("source"))
    uses_animation = update_rate is not CanvasComponentUpdateRate.STATIC
    estimated_cost = _estimated_cost_for_component(component, spec, uses_images=uses_images)
    return CanvasComponentPerformanceProfile(
        component_type=component.type,
        update_rate=update_rate,
        uses_images=uses_images,
        uses_animation=uses_animation,
        estimated_cost=estimated_cost,
        max_update_interval_ms=_max_interval_for_update_rate(update_rate),
    )


def _normalize_mode(mode: str | CanvasPerformanceMode) -> CanvasPerformanceMode:
    try:
        return CanvasPerformanceMode(str(mode).strip().casefold())
    except ValueError:
        return CanvasPerformanceMode.BALANCED


def _update_rate_for_behavior(behavior: CanvasUpdateBehavior) -> CanvasComponentUpdateRate:
    if behavior is CanvasUpdateBehavior.STATIC:
        return CanvasComponentUpdateRate.STATIC
    if behavior is CanvasUpdateBehavior.INTERVAL:
        return CanvasComponentUpdateRate.LOW
    if behavior is CanvasUpdateBehavior.RUNTIME_EVENT_DRIVEN:
        return CanvasComponentUpdateRate.MEDIUM
    if behavior is CanvasUpdateBehavior.USER_INTERACTION_ONLY:
        return CanvasComponentUpdateRate.LOW
    return CanvasComponentUpdateRate.STATIC


def _max_interval_for_update_rate(update_rate: CanvasComponentUpdateRate) -> int | None:
    if update_rate is CanvasComponentUpdateRate.STATIC:
        return None
    return _MIN_INTERVAL_BY_UPDATE_RATE[update_rate]


def _estimated_cost_for_component(
    component: CanvasComponent,
    spec: Any,
    *,
    uses_images: bool,
) -> CanvasComponentEstimatedCost:
    if spec.performance_class is CanvasPerformanceClass.HEAVY:
        return CanvasComponentEstimatedCost.HIGH
    if spec.performance_class is CanvasPerformanceClass.MODERATE or uses_images:
        return CanvasComponentEstimatedCost.MEDIUM
    if component.type in {"clock", "recent.activity"}:
        return CanvasComponentEstimatedCost.MEDIUM
    return CanvasComponentEstimatedCost.LOW


def _is_large_image(component: CanvasComponent, settings: CanvasPerformanceSettings) -> bool:
    if component.type != "image":
        return False
    return component.width > settings.image_resolution_cap or component.height > settings.image_resolution_cap


def _estimate_canvas_cost(
    *,
    live_widgets: int,
    animated_total: int,
    image_components: int,
    high_cost_components: int,
    medium_cost_components: int,
) -> CanvasComponentEstimatedCost:
    if high_cost_components or live_widgets > 80 or animated_total > 96 or image_components > 80:
        return CanvasComponentEstimatedCost.HIGH
    if medium_cost_components or live_widgets > 24 or animated_total > 48 or image_components > 12:
        return CanvasComponentEstimatedCost.MEDIUM
    return CanvasComponentEstimatedCost.LOW


def _profile_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, dict[str, Any]] = {}
    for row in rows:
        component_type = str(row["component_type"])
        bucket = by_type.setdefault(
            component_type,
            {
                "component_type": component_type,
                "count": 0,
                "update_rate": row["update_rate"],
                "estimated_cost": row["estimated_cost"],
                "uses_images": bool(row["uses_images"]),
                "uses_animation": bool(row["uses_animation"]),
                "max_update_interval_ms": row["max_update_interval_ms"],
            },
        )
        bucket["count"] += 1
    return {
        "schema_version": "ritualist.canvas.component_performance_profiles.v1",
        "by_type": [by_type[key] for key in sorted(by_type)],
    }
