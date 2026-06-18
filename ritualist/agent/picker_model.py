from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from ritualist.agent.models import AgentRunState, AgentState
from ritualist.rooms import RoomTemplate, list_rooms


PICKER_MODEL_SCHEMA_VERSION = "ritualist.agent.picker.v1"
HERO_ROOM_NAMES = ("Gaming Room", "Project Room", "Support Desk")
RECENT_RITUAL_LIMIT = 5


@dataclass(frozen=True, slots=True)
class PickerRoom:
    room_id: str
    name: str
    description: str = ""
    category: str = ""
    current: bool = False
    last: bool = False
    ritual_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class PickerRitual:
    recipe_id: str
    title: str
    subtitle: str
    description: str
    room_name: str
    step_count: int
    affected_apps_count: int | None
    intent_summary: str
    readiness_summary: str
    setup_summary: str
    active_summary: str = ""
    recent_summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class PickerAction:
    action: str
    label: str
    enabled: bool = True

    def to_dict(self) -> dict[str, object]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class PickerActiveRitual:
    recipe_id: str
    title: str
    state: str
    summary: str
    step_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return _dataclass_to_dict(self)


@dataclass(frozen=True, slots=True)
class PickerModel:
    schema_version: str
    search_query: str
    current_room: PickerRoom | None
    last_room: PickerRoom | None
    rooms: tuple[PickerRoom, ...]
    recent_rituals: tuple[PickerRitual, ...]
    matching_rituals: tuple[PickerRitual, ...]
    selected_ritual: PickerRitual | None
    active_ritual: PickerActiveRitual | None
    intent_summary: str
    available_actions: tuple[PickerAction, ...]
    browsing_all: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "search_query": self.search_query,
            "current_room": self.current_room.to_dict() if self.current_room else None,
            "last_room": self.last_room.to_dict() if self.last_room else None,
            "rooms": [room.to_dict() for room in self.rooms],
            "recent_rituals": [ritual.to_dict() for ritual in self.recent_rituals],
            "matching_rituals": [ritual.to_dict() for ritual in self.matching_rituals],
            "selected_ritual": self.selected_ritual.to_dict() if self.selected_ritual else None,
            "active_ritual": self.active_ritual.to_dict() if self.active_ritual else None,
            "intent_summary": self.intent_summary,
            "available_actions": [action.to_dict() for action in self.available_actions],
            "browsing_all": self.browsing_all,
        }


RecipeRows = Sequence[tuple[Path, Any, str | None]]
TransparencyProvider = Callable[[Path, Any], Mapping[str, Any]]
DoctorProvider = Callable[[Any], Any]


def build_picker_model(
    *,
    search_query: str = "",
    current_room: str | None = None,
    last_room: str | None = None,
    selected_ritual_id: str | None = None,
    browsing_all: bool = False,
    recipe_rows: RecipeRows | None = None,
    recent_run_records: Sequence[Any] | None = None,
    activity_events: Sequence[Any] | None = None,
    active_state: AgentState | None = None,
    rooms: Sequence[RoomTemplate] | None = None,
    transparency_provider: TransparencyProvider | None = None,
    doctor_provider: DoctorProvider | None = None,
) -> PickerModel:
    hero_rooms = _hero_rooms(rooms)
    current = _resolve_picker_room(current_room, hero_rooms) or (hero_rooms[0] if hero_rooms else None)
    last = _resolve_picker_room(last_room, hero_rooms)

    rows = recipe_rows if recipe_rows is not None else _discover_recipe_rows()
    transparency = transparency_provider or _default_transparency
    doctor = doctor_provider or _default_doctor

    rituals = tuple(
        _ritual_from_recipe(path, recipe, hero_rooms, transparency, doctor)
        for path, recipe, error in rows
        if recipe is not None and error is None
    )

    ritual_counts = _room_counts(rituals)
    rooms_with_counts = tuple(
        _replace_room_flags(
            room,
            current_id=current.room_id if current else "",
            last_id=last.room_id if last else "",
            ritual_count=ritual_counts.get(room.name, 0),
        )
        for room in hero_rooms
    )
    current = _matching_room_by_id(rooms_with_counts, current.room_id) if current else None
    last = _matching_room_by_id(rooms_with_counts, last.room_id) if last else None

    active = _active_ritual_summary(active_state, rituals)
    rituals = tuple(_with_active_summary(ritual, active) for ritual in rituals)
    recent_ids = _recent_recipe_ids(recent_run_records, activity_events)
    recent = tuple(_recent_rituals(rituals, recent_ids))
    rituals = tuple(_with_recent_summary(ritual, recent_ids) for ritual in rituals)

    matching = tuple(
        ritual
        for ritual in rituals
        if _matches_query(ritual, search_query)
        and (browsing_all or current is None or ritual.room_name == current.name)
    )
    selected = _selected_ritual(matching, rituals, selected_ritual_id)
    return PickerModel(
        schema_version=PICKER_MODEL_SCHEMA_VERSION,
        search_query=_clean_text(search_query),
        current_room=current,
        last_room=last,
        rooms=rooms_with_counts,
        recent_rituals=recent,
        matching_rituals=matching,
        selected_ritual=selected,
        active_ritual=active,
        intent_summary=_model_intent_summary(search_query, current, matching, browsing_all=browsing_all),
        available_actions=_available_actions(selected, active, rooms_with_counts),
        browsing_all=bool(browsing_all),
    )


def _discover_recipe_rows() -> RecipeRows:
    from ritualist.recipe_loader import discover_recipes

    return discover_recipes()


def _default_transparency(path: Path, _recipe: Any) -> Mapping[str, Any]:
    from ritualist.recipe_transparency import view_recipe_payload

    return view_recipe_payload(path)


def _default_doctor(recipe: Any) -> Any:
    from ritualist.doctor import build_doctor_report

    return build_doctor_report(recipe)


def _hero_rooms(rooms: Sequence[RoomTemplate] | None) -> tuple[PickerRoom, ...]:
    available = tuple(rooms if rooms is not None else list_rooms())
    by_name = {room.name: room for room in available}
    return tuple(
        PickerRoom(
            room_id=room.room_id,
            name=room.name,
            description=room.description,
            category=room.category,
        )
        for name in HERO_ROOM_NAMES
        if (room := by_name.get(name)) is not None
    )


def _resolve_picker_room(value: str | None, rooms: Sequence[PickerRoom]) -> PickerRoom | None:
    text = _clean_text(value).casefold()
    if not text:
        return None
    for room in rooms:
        candidates = {
            room.room_id.casefold(),
            room.name.casefold(),
            room.category.casefold(),
        }
        if text in candidates:
            return room
    return None


def _ritual_from_recipe(
    path: Path,
    recipe: Any,
    rooms: Sequence[PickerRoom],
    transparency_provider: TransparencyProvider,
    doctor_provider: DoctorProvider,
) -> PickerRitual:
    transparency = _safe_transparency(path, recipe, transparency_provider)
    doctor = _safe_doctor(recipe, doctor_provider)
    room = _room_for_recipe(recipe, rooms)
    recipe_id = str(getattr(recipe, "id", "") or "").strip()
    return PickerRitual(
        recipe_id=recipe_id,
        title=_recipe_title(recipe, recipe_id),
        subtitle=_recipe_subtitle(recipe),
        description=_clean_text(getattr(recipe, "description", None)),
        room_name=room.name if room else "",
        step_count=len(getattr(recipe, "execution_steps", ()) or ()),
        affected_apps_count=_affected_apps_count(recipe),
        intent_summary=_intent_summary(recipe, transparency),
        readiness_summary=_readiness_summary(doctor),
        setup_summary=_setup_summary(transparency),
    )


def _safe_transparency(
    path: Path,
    recipe: Any,
    provider: TransparencyProvider,
) -> Mapping[str, Any]:
    try:
        payload = provider(path, recipe)
    except Exception:  # noqa: BLE001 - picker should degrade to recipe metadata.
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _safe_doctor(recipe: Any, provider: DoctorProvider) -> Any:
    try:
        return provider(recipe)
    except Exception:  # noqa: BLE001 - readiness is advisory in the picker.
        return None


def _recipe_title(recipe: Any, recipe_id: str) -> str:
    card = _recipe_card(recipe)
    return _first_text(
        getattr(card, "title", None),
        getattr(recipe, "name", None),
        _title_from_id(recipe_id),
        fallback="Untitled Ritual",
    )


def _recipe_subtitle(recipe: Any) -> str:
    card = _recipe_card(recipe)
    return _first_text(
        getattr(card, "subtitle", None),
        getattr(recipe, "description", None),
        fallback="Ready for local review",
    )


def _recipe_card(recipe: Any) -> Any:
    home = getattr(recipe, "home", None)
    if home is None:
        return None
    return getattr(home, "card", None)


def _room_for_recipe(recipe: Any, rooms: Sequence[PickerRoom]) -> PickerRoom | None:
    category = _recipe_category(recipe).casefold()
    name_by_room = {room.name: room for room in rooms}
    if "gaming" in category:
        return name_by_room.get("Gaming Room")
    if "support" in category or "helpdesk" in category:
        return name_by_room.get("Support Desk")
    if any(token in category for token in ("project", "coding", "work", "research")):
        return name_by_room.get("Project Room")
    return name_by_room.get("Project Room") if rooms else None


def _recipe_category(recipe: Any) -> str:
    home = getattr(recipe, "home", None)
    return _clean_text(getattr(home, "category", None)) if home is not None else ""


def _intent_summary(recipe: Any, transparency: Mapping[str, Any]) -> str:
    plan = transparency.get("plain_language_plan")
    if isinstance(plan, Sequence) and not isinstance(plan, str):
        for item in plan:
            text = _clean_text(item)
            if text:
                return text.removeprefix("Purpose:").strip() or text
    return _first_text(
        getattr(recipe, "description", None),
        getattr(recipe, "name", None),
        fallback="Review the ritual before running.",
    )


def _readiness_summary(doctor: Any) -> str:
    if doctor is None:
        return "Readiness not checked"
    payload = doctor.to_dict() if hasattr(doctor, "to_dict") else doctor
    if not isinstance(payload, Mapping):
        return "Readiness not checked"
    compatibility = payload.get("compatibility")
    if not isinstance(compatibility, Mapping):
        return "Readiness not checked"
    status = _clean_text(compatibility.get("status")).replace("_", " ")
    errors = _int_value(compatibility.get("errors_count"))
    warnings = _int_value(compatibility.get("warnings_count"))
    if errors:
        return f"Needs attention: {errors} error{'s' if errors != 1 else ''}"
    if warnings:
        return f"Ready with {warnings} warning{'s' if warnings != 1 else ''}"
    if status:
        return status.title()
    return "Readiness not checked"


def _setup_summary(transparency: Mapping[str, Any]) -> str:
    fields_value = transparency.get("setup_fields")
    if not isinstance(fields_value, Sequence) or isinstance(fields_value, str):
        return "No setup fields"
    fields = [field for field in fields_value if isinstance(field, Mapping) and field.get("editable")]
    overridden = [field for field in fields if field.get("overridden")]
    if not fields:
        return "No setup fields"
    label = "field" if len(fields) == 1 else "fields"
    if overridden:
        return f"{len(fields)} setup {label}, {len(overridden)} overridden"
    return f"{len(fields)} setup {label}"


def _affected_apps_count(recipe: Any) -> int | None:
    names: set[str] = set()
    for step in getattr(recipe, "execution_steps", ()) or ():
        action = _clean_text(getattr(step, "action", None))
        if action in {"browser.open", "browser.open_native"}:
            names.add(_first_text(getattr(step, "browser", None), fallback="Default browser"))
        elif action == "app.launch":
            names.add(_app_label(getattr(step, "command", "")))
        elif action.startswith("window.") or action.startswith("wait.for_window"):
            names.add(
                _first_text(
                    getattr(step, "title_contains", None),
                    getattr(step, "window_title_contains", None),
                    getattr(step, "process_name", None),
                    fallback="Desktop app",
                )
            )
        elif action.startswith("target."):
            names.add(_first_text(getattr(step, "target", None), fallback="Target app"))
    return len({name for name in names if name}) if names else None


def _app_label(command: object) -> str:
    text = _clean_text(command)
    if not text:
        return "Local app"
    first = text.split()[0].strip("\"'")
    return Path(first.replace("\\", "/")).name or "Local app"


def _room_counts(rituals: Sequence[PickerRitual]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ritual in rituals:
        if ritual.room_name:
            counts[ritual.room_name] = counts.get(ritual.room_name, 0) + 1
    return counts


def _replace_room_flags(
    room: PickerRoom,
    *,
    current_id: str,
    last_id: str,
    ritual_count: int,
) -> PickerRoom:
    return PickerRoom(
        room_id=room.room_id,
        name=room.name,
        description=room.description,
        category=room.category,
        current=room.room_id == current_id,
        last=room.room_id == last_id,
        ritual_count=ritual_count,
    )


def _matching_room_by_id(rooms: Sequence[PickerRoom], room_id: str) -> PickerRoom | None:
    for room in rooms:
        if room.room_id == room_id:
            return room
    return None


def _recent_recipe_ids(
    recent_run_records: Sequence[Any] | None,
    activity_events: Sequence[Any] | None,
) -> tuple[str, ...]:
    records = recent_run_records if recent_run_records is not None else _recent_runs()
    events = activity_events if activity_events is not None else _activity_events()
    ordered: list[str] = []
    for record in records:
        _append_unique(ordered, _recipe_id_from_record(record))
    for event in events:
        _append_unique(ordered, _recipe_id_from_event(event))
    return tuple(ordered)


def _recent_runs() -> Sequence[Any]:
    from ritualist.run_logs import list_recent_runs

    return list_recent_runs(limit=25)


def _activity_events() -> Sequence[Any]:
    from ritualist.activity_journal import ActivityJournal

    return ActivityJournal().read(limit=25)


def _recipe_id_from_record(record: Any) -> str:
    metadata = getattr(record, "metadata", None)
    if metadata is None and isinstance(record, Mapping):
        metadata = record.get("metadata")
    if isinstance(metadata, Mapping):
        return _clean_text(metadata.get("recipe_id"))
    return ""


def _recipe_id_from_event(event: Any) -> str:
    payload = getattr(event, "payload", None)
    if payload is None and isinstance(event, Mapping):
        payload = event.get("payload")
    if isinstance(payload, Mapping):
        return _clean_text(payload.get("recipe_id"))
    return ""


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _recent_rituals(
    rituals: Sequence[PickerRitual],
    recent_ids: Sequence[str],
) -> list[PickerRitual]:
    by_id = {ritual.recipe_id: ritual for ritual in rituals}
    recent: list[PickerRitual] = []
    for recipe_id in recent_ids:
        ritual = by_id.get(recipe_id)
        if ritual is None:
            continue
        recent.append(_with_recent_summary(ritual, recent_ids))
        if len(recent) >= RECENT_RITUAL_LIMIT:
            break
    return recent


def _with_recent_summary(ritual: PickerRitual, recent_ids: Sequence[str]) -> PickerRitual:
    if ritual.recipe_id not in recent_ids:
        return ritual
    position = list(recent_ids).index(ritual.recipe_id) + 1
    return PickerRitual(
        **{
            **_dataclass_to_dict(ritual),
            "recent_summary": "Most recent ritual" if position == 1 else f"Recent ritual #{position}",
        }
    )


def _active_ritual_summary(
    active_state: AgentState | None,
    rituals: Sequence[PickerRitual],
) -> PickerActiveRitual | None:
    if active_state is None or not active_state.active_ritual_id:
        return None
    by_id = {ritual.recipe_id: ritual for ritual in rituals}
    ritual = by_id.get(active_state.active_ritual_id)
    title = _first_text(
        active_state.active_ritual_name,
        ritual.title if ritual else "",
        fallback="Active ritual",
    )
    step = active_state.current_step.name if active_state.current_step else ""
    state = _run_state_value(active_state.state)
    summary = f"{title} is {state.replace('_', ' ')}"
    if step:
        summary = f"{summary}: {step}"
    return PickerActiveRitual(
        recipe_id=active_state.active_ritual_id,
        title=title,
        state=state,
        summary=summary,
        step_count=max(0, int(active_state.step_count or 0)),
    )


def _with_active_summary(
    ritual: PickerRitual,
    active: PickerActiveRitual | None,
) -> PickerRitual:
    if active is None or ritual.recipe_id != active.recipe_id:
        return ritual
    return PickerRitual(
        **{
            **_dataclass_to_dict(ritual),
            "active_summary": active.summary,
        }
    )


def _run_state_value(state: AgentRunState | str) -> str:
    if isinstance(state, AgentRunState):
        return state.value
    return _clean_text(state) or "active"


def _matches_query(ritual: PickerRitual, query: str) -> bool:
    normalized = _clean_text(query).casefold()
    if not normalized:
        return True
    haystack = " ".join(
        (
            ritual.recipe_id,
            ritual.title,
            ritual.subtitle,
            ritual.description,
            ritual.room_name,
            ritual.intent_summary,
        )
    ).casefold()
    return all(term in haystack for term in normalized.split())


def _selected_ritual(
    matching: Sequence[PickerRitual],
    all_rituals: Sequence[PickerRitual],
    selected_ritual_id: str | None,
) -> PickerRitual | None:
    recipe_id = _clean_text(selected_ritual_id)
    if not recipe_id:
        return None
    for ritual in (*matching, *all_rituals):
        if ritual.recipe_id == recipe_id:
            return ritual
    return None


def _model_intent_summary(
    search_query: str,
    current_room: PickerRoom | None,
    matching: Sequence[PickerRitual],
    *,
    browsing_all: bool,
) -> str:
    room_text = "all Rooms" if browsing_all or current_room is None else current_room.name
    query = _clean_text(search_query)
    if query:
        return f"{len(matching)} ritual{'s' if len(matching) != 1 else ''} match \"{query}\" in {room_text}"
    return f"{len(matching)} ritual{'s' if len(matching) != 1 else ''} available in {room_text}"


def _available_actions(
    selected: PickerRitual | None,
    active: PickerActiveRitual | None,
    rooms: Sequence[PickerRoom],
) -> tuple[PickerAction, ...]:
    return (
        PickerAction("select_ritual", "Select ritual", enabled=True),
        PickerAction("open_preflight", "Open preflight", enabled=selected is not None),
        PickerAction("browse_all", "Browse all", enabled=True),
        PickerAction("open_builder", "Open Builder", enabled=True),
        PickerAction("change_room", "Change Room", enabled=bool(rooms)),
        PickerAction("return_to_active", "Return to active ritual", enabled=active is not None),
    )


def _first_text(*values: object, fallback: str) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return fallback


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


def _title_from_id(recipe_id: str) -> str:
    return recipe_id.replace("_", " ").replace("-", " ").title()


def _int_value(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _dataclass_to_dict(instance: object) -> dict[str, Any]:
    return {field.name: getattr(instance, field.name) for field in fields(instance)}


__all__ = [
    "HERO_ROOM_NAMES",
    "PICKER_MODEL_SCHEMA_VERSION",
    "RECENT_RITUAL_LIMIT",
    "PickerAction",
    "PickerActiveRitual",
    "PickerModel",
    "PickerRitual",
    "PickerRoom",
    "build_picker_model",
]
