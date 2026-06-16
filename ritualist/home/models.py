from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from threading import Lock
from typing import Any

from ritualist.event_coalescing import EventCoalescer


@dataclass(frozen=True)
class HomeCategory:
    label: str


HOME_CATEGORIES = (
    HomeCategory("Gaming"),
    HomeCategory("Media"),
    HomeCategory("Coding"),
    HomeCategory("News"),
    HomeCategory("Helpdesk"),
    HomeCategory("Settings"),
)


class HomeCardStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    WARNING = "warning"
    FAILED = "failed"
    DISABLED = "disabled"


class HomeLastRunStatus(StrEnum):
    NONE = "none"
    SUCCESS = "success"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class HomeCard:
    id: str
    title: str
    category: str
    subtitle: str = ""
    description: str = ""
    status: HomeCardStatus = HomeCardStatus.READY
    last_run_status: HomeLastRunStatus = HomeLastRunStatus.NONE
    accent: str = "#3dd6a5"
    image: str = ""

    def to_qml(self) -> dict[str, str]:
        return {field.name: _qml_string(getattr(self, field.name)) for field in fields(self)}


@dataclass(frozen=True)
class HomeRuntimeEvent:
    card_id: str
    title: str | None = None
    subtitle: str | None = None
    description: str | None = None
    status: HomeCardStatus | None = None
    last_run_status: HomeLastRunStatus | None = None
    accent: str | None = None
    image: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return ("home-card", self.card_id)


@dataclass
class HomeModel:
    cards: list[HomeCard] = field(default_factory=list)

    def get_card(self, card_id: str) -> HomeCard:
        return self.cards[self._card_index(card_id)]

    def apply_runtime_event(
        self,
        event: HomeRuntimeEvent | Mapping[str, Any],
    ) -> HomeCard:
        parsed = event if isinstance(event, HomeRuntimeEvent) else _runtime_event_from_mapping(event)
        index = self._card_index(parsed.card_id)
        updates = {
            field.name: getattr(parsed, field.name)
            for field in fields(parsed)
            if field.name != "card_id" and getattr(parsed, field.name) is not None
        }
        updated = replace(self.cards[index], **updates)
        self.cards[index] = updated
        return updated

    def to_qml(self) -> dict[str, object]:
        return {
            "categories": [{"label": category.label} for category in HOME_CATEGORIES],
            "cards": [card.to_qml() for card in self.cards],
        }

    def _card_index(self, card_id: str) -> int:
        for index, card in enumerate(self.cards):
            if card.id == card_id:
                return index
        raise KeyError(card_id)


class HomeEventBridge:
    """Thread-safe bridge from background mock events into the Home model."""

    def __init__(
        self,
        model: HomeModel,
        *,
        target_hz: float = 30.0,
        clock: Any | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {"target_hz": target_hz}
        if clock is not None:
            kwargs["clock"] = clock
        self._coalescer = EventCoalescer(**kwargs)
        self._model = model
        self._lock = Lock()
        self._applied_count = 0

    @property
    def interval_seconds(self) -> float:
        return self._coalescer.interval_seconds

    @property
    def has_pending(self) -> bool:
        with self._lock:
            return self._coalescer.has_pending

    @property
    def applied_count(self) -> int:
        return self._applied_count

    def queue_runtime_event(self, event: HomeRuntimeEvent) -> None:
        with self._lock:
            self._coalescer.put(event.key, event)

    def apply_due(self, *, now: float | None = None) -> list[HomeRuntimeEvent]:
        with self._lock:
            updates = self._coalescer.emit_due(now=now)
        return self._apply(updates.values())

    def flush(self, *, now: float | None = None) -> list[HomeRuntimeEvent]:
        with self._lock:
            updates = self._coalescer.flush(now=now)
        return self._apply(updates.values())

    def _apply(self, events: Any) -> list[HomeRuntimeEvent]:
        applied: list[HomeRuntimeEvent] = []
        for event in events:
            if not isinstance(event, HomeRuntimeEvent):
                continue
            try:
                self._model.apply_runtime_event(event)
            except KeyError:
                continue
            applied.append(event)
        self._applied_count += len(applied)
        return applied


def generate_mock_home_cards() -> list[HomeCard]:
    cards: list[HomeCard] = []
    accents = ("#3dd6a5", "#6aa9ff", "#f2c94c", "#eb5757", "#bb86fc", "#56ccf2")
    statuses = (
        HomeCardStatus.READY,
        HomeCardStatus.RUNNING,
        HomeCardStatus.SUCCESS,
        HomeCardStatus.WARNING,
        HomeCardStatus.FAILED,
        HomeCardStatus.DISABLED,
    )
    last_run_statuses = (
        HomeLastRunStatus.NONE,
        HomeLastRunStatus.SUCCESS,
        HomeLastRunStatus.STOPPED,
        HomeLastRunStatus.FAILED,
    )
    status_subtitles = {
        HomeCardStatus.READY: "Ready for local launch",
        HomeCardStatus.RUNNING: "Runtime event stream active",
        HomeCardStatus.SUCCESS: "Last run completed",
        HomeCardStatus.WARNING: "Needs a confirmation gate",
        HomeCardStatus.FAILED: "Requires local attention",
        HomeCardStatus.DISABLED: "Disabled in this profile",
    }

    for index in range(120):
        category = HOME_CATEGORIES[index % len(HOME_CATEGORIES)]
        status = statuses[index % len(statuses)]
        card_number = index + 1
        cards.append(
            HomeCard(
                id=f"{category.label.lower()}-{card_number:03d}",
                title=f"{category.label} Ritual {card_number:03d}",
                category=category.label,
                subtitle=status_subtitles[status],
                description="Mock Home data for the QML bridge without touching desktop state.",
                status=status,
                last_run_status=last_run_statuses[index % len(last_run_statuses)],
                accent=accents[index % len(accents)],
                image="",
            )
        )
    return cards


def create_mock_home_model() -> HomeModel:
    return HomeModel(cards=generate_mock_home_cards())


def _runtime_event_from_mapping(event: Mapping[str, Any]) -> HomeRuntimeEvent:
    return HomeRuntimeEvent(
        card_id=str(event["card_id"]),
        title=_optional_string(event.get("title")),
        subtitle=_optional_string(event.get("subtitle")),
        description=_optional_string(event.get("description")),
        status=_optional_enum(HomeCardStatus, event.get("status")),
        last_run_status=_optional_enum(HomeLastRunStatus, event.get("last_run_status")),
        accent=_optional_string(event.get("accent")),
        image=_optional_string(event.get("image")),
    )


def _optional_enum(enum_type: type[StrEnum], value: object) -> Any:
    if value is None or isinstance(value, enum_type):
        return value
    return enum_type(str(value))


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _qml_string(value: object) -> str:
    if isinstance(value, StrEnum):
        return value.value
    if value is None:
        return ""
    return str(value)
