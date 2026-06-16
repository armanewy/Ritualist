from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from pathlib import Path
from threading import Lock
from typing import Any

from ritualist.config import DEFAULT_HOME_CATEGORIES
from ritualist.event_coalescing import EventCoalescer

OTHER_HOME_CATEGORY = "Other"
DEFAULT_RECIPE_CATEGORY = "Recipes"
DEFAULT_RECIPE_SUBTITLE = "Ready to run locally"
DEFAULT_RECIPE_DESCRIPTION = "No description provided."
DEFAULT_RECIPE_ACCENT = "#3dd6a5"


@dataclass(frozen=True)
class HomeCategory:
    label: str


HOME_CATEGORIES = tuple(HomeCategory(label) for label in DEFAULT_HOME_CATEGORIES)


class HomeCardStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    WARNING = "warning"
    FAILED = "failed"
    DISABLED = "disabled"


class HomeLastRunStatus(StrEnum):
    NONE = "none"
    RUNNING = "running"
    SUCCESS = "success"
    STOPPED = "stopped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class HomeDoctorStatus(StrEnum):
    NOT_CHECKED = "not_checked"


@dataclass(frozen=True)
class HomeCard:
    id: str
    title: str
    category: str
    subtitle: str = ""
    description: str = ""
    status: HomeCardStatus = HomeCardStatus.READY
    last_run_status: HomeLastRunStatus = HomeLastRunStatus.NONE
    doctor_status: HomeDoctorStatus = HomeDoctorStatus.NOT_CHECKED
    accent: str = "#3dd6a5"
    image: str = ""
    wait_action: str = ""
    wait_target: str = ""
    wait_started_at: str = ""
    wait_elapsed_seconds: str = ""
    wait_timeout_seconds: str = ""
    keep_open_active: bool = False

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
    doctor_status: HomeDoctorStatus | None = None
    accent: str | None = None
    image: str | None = None
    wait_action: str | None = None
    wait_target: str | None = None
    wait_started_at: str | None = None
    wait_elapsed_seconds: str | None = None
    wait_timeout_seconds: str | None = None
    keep_open_active: bool | None = None

    @property
    def key(self) -> tuple[str, str]:
        return ("home-card", self.card_id)


@dataclass
class HomeModel:
    cards: list[HomeCard] = field(default_factory=list)
    categories: tuple[HomeCategory | str, ...] = field(default_factory=lambda: HOME_CATEGORIES)

    def __post_init__(self) -> None:
        self.categories = resolve_home_categories(self.categories)

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
        categories = resolve_home_categories(self.categories, self.cards)
        return {
            "categories": [{"label": category.label} for category in categories],
            "cards": [_card_for_qml(card).to_qml() for card in self.cards],
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

    def replace_model(self, model: HomeModel) -> None:
        with self._lock:
            self._model = model

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


def resolve_home_categories(
    configured: Sequence[HomeCategory | str] | None = None,
    cards: Sequence[HomeCard] = (),
) -> tuple[HomeCategory, ...]:
    labels = _category_labels(configured)
    if not labels:
        labels = list(DEFAULT_HOME_CATEGORIES)

    seen = {label.casefold() for label in labels}
    for card in cards:
        label = _home_category_label(card.category) or OTHER_HOME_CATEGORY
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)

    return tuple(HomeCategory(label) for label in labels)


def generate_mock_home_cards(
    categories: Sequence[HomeCategory | str] | None = None,
) -> list[HomeCard]:
    cards: list[HomeCard] = []
    resolved_categories = resolve_home_categories(categories)
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
        category = resolved_categories[index % len(resolved_categories)]
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


def create_mock_home_model(
    categories: Sequence[HomeCategory | str] | None = None,
) -> HomeModel:
    return HomeModel(cards=generate_mock_home_cards(categories), categories=resolve_home_categories(categories))


@dataclass
class HomeRunHistoryCache:
    """Bounded, reusable lookup of latest run status by recipe id."""

    limit: int = 100
    base_dir: Path | None = None
    _last_status_by_recipe_id: dict[str, HomeLastRunStatus] = field(default_factory=dict)
    _last_summary_by_recipe_id: dict[str, Any] = field(default_factory=dict)
    _loaded: bool = False

    def refresh(self) -> None:
        from ritualist.run_logs import list_recent_runs, summarize_run_record

        latest: dict[str, HomeLastRunStatus] = {}
        summaries: dict[str, Any] = {}
        for record in list_recent_runs(limit=self.limit, base_dir=self.base_dir):
            recipe_id = _optional_string(record.metadata.get("recipe_id"))
            if not recipe_id or recipe_id in latest:
                continue
            latest[recipe_id] = _last_run_status_from_metadata(record.metadata)
            summaries[recipe_id] = summarize_run_record(record)
        self._last_status_by_recipe_id = latest
        self._last_summary_by_recipe_id = summaries
        self._loaded = True

    def get(self, recipe_id: str) -> HomeLastRunStatus:
        if not self._loaded:
            self.refresh()
        return self._last_status_by_recipe_id.get(recipe_id, HomeLastRunStatus.NONE)

    def get_summary(self, recipe_id: str) -> Any | None:
        if not self._loaded:
            self.refresh()
        return self._last_summary_by_recipe_id.get(recipe_id)


def create_installed_home_model(
    *,
    categories: Sequence[HomeCategory | str] | None = None,
    run_history_cache: HomeRunHistoryCache | None = None,
    recipe_rows: Sequence[tuple[Path, Any, str | None]] | None = None,
) -> HomeModel:
    cards = load_installed_home_cards(
        run_history_cache=run_history_cache,
        recipe_rows=recipe_rows,
    )
    return HomeModel(cards=cards, categories=resolve_home_categories(categories, cards))


def load_installed_home_cards(
    *,
    run_history_cache: HomeRunHistoryCache | None = None,
    recipe_rows: Sequence[tuple[Path, Any, str | None]] | None = None,
) -> list[HomeCard]:
    if recipe_rows is None:
        from ritualist.recipe_loader import discover_recipes

        rows = discover_recipes()
    else:
        rows = recipe_rows

    history = run_history_cache or HomeRunHistoryCache()
    cards: list[HomeCard] = []
    for _path, recipe, _error in rows:
        if recipe is None:
            continue
        cards.append(_recipe_home_card(recipe, history.get(str(recipe.id))))
    return cards


def _runtime_event_from_mapping(event: Mapping[str, Any]) -> HomeRuntimeEvent:
    return HomeRuntimeEvent(
        card_id=str(event["card_id"]),
        title=_optional_string(event.get("title")),
        subtitle=_optional_string(event.get("subtitle")),
        description=_optional_string(event.get("description")),
        status=_optional_enum(HomeCardStatus, event.get("status")),
        last_run_status=_optional_enum(HomeLastRunStatus, event.get("last_run_status")),
        doctor_status=_optional_enum(HomeDoctorStatus, event.get("doctor_status")),
        accent=_optional_string(event.get("accent")),
        image=_optional_string(event.get("image")),
        wait_action=_optional_string(event.get("wait_action")),
        wait_target=_optional_string(event.get("wait_target")),
        wait_started_at=_optional_string(event.get("wait_started_at")),
        wait_elapsed_seconds=_optional_string(event.get("wait_elapsed_seconds")),
        wait_timeout_seconds=_optional_string(event.get("wait_timeout_seconds")),
        keep_open_active=_optional_bool(event.get("keep_open_active")),
    )


def _recipe_home_card(recipe: Any, last_run_status: HomeLastRunStatus) -> HomeCard:
    recipe_id = str(recipe.id)
    card_metadata = _recipe_home_card_metadata(recipe)
    title = _display_string(
        getattr(card_metadata, "title", None),
        fallback=_display_string(getattr(recipe, "name", None), fallback=_title_from_id(recipe_id)),
    )
    description = _display_string(getattr(recipe, "description", None), fallback=DEFAULT_RECIPE_DESCRIPTION)
    return HomeCard(
        id=recipe_id,
        title=title,
        category=_recipe_category(recipe),
        subtitle=_recipe_subtitle(recipe, fallback=DEFAULT_RECIPE_SUBTITLE),
        description=description,
        status=_card_status_from_last_run(last_run_status),
        last_run_status=last_run_status,
        doctor_status=HomeDoctorStatus.NOT_CHECKED,
        accent=_display_string(getattr(card_metadata, "accent", None), fallback=DEFAULT_RECIPE_ACCENT),
        image=_recipe_thumbnail_url(getattr(card_metadata, "image", None)),
    )


def _recipe_category(recipe: Any) -> str:
    return _display_string(
        _recipe_home_value(recipe, "category"),
        fallback=DEFAULT_RECIPE_CATEGORY,
    )


def _recipe_subtitle(recipe: Any, *, fallback: str) -> str:
    card_metadata = _recipe_home_card_metadata(recipe)
    return _display_string(
        getattr(card_metadata, "subtitle", None),
        fallback=_display_string(getattr(recipe, "description", None), fallback=fallback),
    )


def _recipe_home_value(recipe: Any, key: str) -> object:
    home = getattr(recipe, "home", None)
    if home is not None:
        return getattr(home, key, None)
    return None


def _recipe_home_card_metadata(recipe: Any) -> Any | None:
    home = getattr(recipe, "home", None)
    if home is None:
        return None
    return getattr(home, "card", None)


def _recipe_thumbnail_url(image_path: object) -> str:
    raw = str(image_path or "").strip()
    if not raw:
        return ""
    from ritualist.home.assets import HomeThumbnailCache

    return HomeThumbnailCache().ensure_thumbnail(raw).thumbnail_url


def _display_string(value: object, *, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _title_from_id(recipe_id: str) -> str:
    return recipe_id.replace("_", " ").replace("-", " ").title() or "Untitled Recipe"


def _categories_from_cards(cards: Sequence[HomeCard]) -> tuple[HomeCategory, ...]:
    categories: list[HomeCategory] = []
    seen: set[str] = set()
    for card in cards:
        category = _home_category_label(card.category) or DEFAULT_RECIPE_CATEGORY
        key = category.casefold()
        if key in seen:
            continue
        categories.append(HomeCategory(category))
        seen.add(key)
    return tuple(categories) or (HomeCategory(DEFAULT_RECIPE_CATEGORY),)


def _last_run_status_from_metadata(metadata: Mapping[str, Any]) -> HomeLastRunStatus:
    raw_status = metadata.get("final_state") or metadata.get("current_run_state") or metadata.get("status")
    status = str(raw_status or "").strip().lower()
    if status == "success":
        return HomeLastRunStatus.SUCCESS
    if status in {"failed", "error"}:
        return HomeLastRunStatus.FAILED
    if status in {"stopped", "cancelled", "canceled"}:
        return HomeLastRunStatus.STOPPED
    if status == "interrupted":
        return HomeLastRunStatus.INTERRUPTED
    if status in {"running", "waiting", "paused", "confirming", "stopping"}:
        return HomeLastRunStatus.RUNNING
    return HomeLastRunStatus.NONE


def _card_status_from_last_run(last_run_status: HomeLastRunStatus) -> HomeCardStatus:
    if last_run_status is HomeLastRunStatus.RUNNING:
        return HomeCardStatus.RUNNING
    if last_run_status is HomeLastRunStatus.SUCCESS:
        return HomeCardStatus.SUCCESS
    if last_run_status is HomeLastRunStatus.FAILED:
        return HomeCardStatus.FAILED
    if last_run_status in {HomeLastRunStatus.STOPPED, HomeLastRunStatus.INTERRUPTED}:
        return HomeCardStatus.WARNING
    return HomeCardStatus.READY


def _optional_enum(enum_type: type[StrEnum], value: object) -> Any:
    if value is None or isinstance(value, enum_type):
        return value
    return enum_type(str(value))


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: object) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _category_labels(configured: Sequence[HomeCategory | str] | None) -> list[str]:
    if configured is None:
        return list(DEFAULT_HOME_CATEGORIES)

    labels: list[str] = []
    seen: set[str] = set()
    for category in configured:
        label = _home_category_label(category.label if isinstance(category, HomeCategory) else category)
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return labels


def _card_for_qml(card: HomeCard) -> HomeCard:
    category = _home_category_label(card.category) or OTHER_HOME_CATEGORY
    if category == card.category:
        return card
    return replace(card, category=category)


def _home_category_label(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _qml_string(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, StrEnum):
        return value.value
    if value is None:
        return ""
    return str(value)
