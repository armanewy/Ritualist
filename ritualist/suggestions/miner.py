from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

from ritualist.activity_signals import (
    ALLOWED_ACTIVITY_SOURCE_IDS,
    FORBIDDEN_ACTIVITY_METADATA_KEYS,
    FORBIDDEN_ACTIVITY_METADATA_KEY_TOKENS,
    FORBIDDEN_ACTIVITY_SOURCE_IDS,
    OPEN_WINDOWS_SOURCE_ID,
    RECENT_ITEMS_SOURCE_ID,
    RITUALIST_JOURNAL_SOURCE_ID,
    ActivityCollectionResult,
    ActivitySignal,
    normalize_activity_id,
)
from ritualist.suggestions.models import (
    Suggestion,
    SuggestionKind,
    SuggestionPrivacyLevel,
)


MIN_PATTERN_REPETITIONS = 2
DEFAULT_MAX_SUGGESTIONS = 20
DEFAULT_CLUSTER_WINDOW = 4

_PROMOTED_ROOM_NAMES = {
    "gaming": "Gaming Room",
    "gaming_desktop": "Gaming Room",
    "project": "Project Room",
    "project_room": "Project Room",
    "support_desk": "Support Desk",
    "helpdesk": "Support Desk",
    "helpdesk_desktop": "Support Desk",
}
_INTERNAL_ROOM_IDS = frozenset({"minimal", "minimal_desktop"})
_PAIR_CATEGORIES = (
    ("app", "folder"),
    ("app", "domain"),
    ("ritual", "shortcut"),
)
_SENSITIVE_LABEL_TOKENS = frozenset(
    {
        "2fa",
        "auth",
        "credential",
        "keychain",
        "password",
        "private",
        "secret",
        "token",
        "vault",
    }
)
_FORBIDDEN_LABEL_TOKENS = frozenset(
    {
        "browser_history",
        "browserhistory",
        "capture",
        "click_coordinate",
        "coordinate",
        "history",
        "keylogging",
        "keyboard_logger",
        "keyboardlogger",
        "key_log",
        "key_logger",
        "keylog",
        "keylogger",
        "keystroke",
        "ocr",
        "recall",
        "recorder",
        "recording",
        "screenshot",
        "screen_recorder",
        "screenrecorder",
        "screencapture",
        "teach_by_watching",
        "teachbywatching",
        "watch_me",
        "watchme",
        "windows_recall",
        "windowsrecall",
    }
)
_EXECUTABLE_SUFFIXES = frozenset(
    {".bat", ".cmd", ".com", ".exe", ".js", ".ps1", ".py", ".sh", ".vbs"}
)
_PATH_RE = re.compile(r"(^[A-Za-z]:[\\/]|^[/\\~]|[/\\])")
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_URI_SCHEME_TOKEN_RE = re.compile(
    r"(?<![\w:])(?:\[)?([A-Za-z][A-Za-z0-9+.-]*):"
    r"(?://[^\s,;\]]+|[^\s,;\]]+)(?:\])?"
)
_HTML_OR_SCRIPT_MARKER_RE = re.compile(
    r"<\s*/?\s*[A-Za-z][^>]*>"
    r"|\bon[A-Za-z]+\s*="
    r"|\bjavascript\b"
    r"|\balert\s*\(",
    re.IGNORECASE,
)
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/](?![\\/])")
_PROTOCOL_RELATIVE_URL_RE = re.compile(
    r"^//(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?:[:/]|$)",
    re.IGNORECASE,
)
_DOMAIN_RE = re.compile(
    r"^(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}(?::\d{1,5})?(?:/.*)?$",
    re.IGNORECASE,
)
_IPV4_LOCATOR_RE = re.compile(
    r"^(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?:[/?#].*)?$"
)


@dataclass(frozen=True)
class PatternMinerConfig:
    min_repetitions: int = MIN_PATTERN_REPETITIONS
    max_suggestions: int = DEFAULT_MAX_SUGGESTIONS
    cluster_window: int = DEFAULT_CLUSTER_WINDOW

    def __post_init__(self) -> None:
        object.__setattr__(self, "min_repetitions", max(2, int(self.min_repetitions)))
        object.__setattr__(self, "max_suggestions", max(0, int(self.max_suggestions)))
        object.__setattr__(self, "cluster_window", max(2, int(self.cluster_window)))


@dataclass(frozen=True)
class _Observation:
    category: str
    key: str
    label: str
    source_id: str
    position: int
    signal_id: int
    context_id: str = ""
    risk: int = 0


@dataclass
class _Aggregate:
    category: str
    key: str
    label: str
    count: int = 0
    risk: int = 0
    sources: set[str] | None = None

    def add(self, observation: _Observation) -> None:
        self.count += 1
        self.risk += observation.risk
        if self.sources is None:
            self.sources = set()
        self.sources.add(observation.source_id)

    @property
    def source_tuple(self) -> tuple[str, ...]:
        return tuple(sorted(self.sources or ()))


@dataclass(frozen=True)
class _PairAggregate:
    left: _Aggregate
    right: _Aggregate
    count: int
    risk: int
    sources: tuple[str, ...]


class SuggestionMiner:
    def __init__(self, config: PatternMinerConfig | None = None) -> None:
        self.config = config or PatternMinerConfig()

    def mine(self, activity: object) -> tuple[Suggestion, ...]:
        observations = tuple(_observations_from_activity(activity))
        singles = _aggregate_observations(observations)
        suggestions: list[Suggestion] = []

        for aggregate in _ranked_singles(singles, self.config.min_repetitions):
            suggestion = _single_suggestion(aggregate, self.config.min_repetitions)
            if suggestion is not None:
                suggestions.append(suggestion)

        for pair in _ranked_pairs(
            observations,
            singles,
            min_repetitions=self.config.min_repetitions,
            cluster_window=self.config.cluster_window,
        ):
            suggestions.append(_pair_suggestion(pair, self.config.min_repetitions))

        for room in _ranked_room_clusters(
            observations,
            singles,
            min_repetitions=self.config.min_repetitions,
            cluster_window=self.config.cluster_window,
        ):
            suggestions.append(_room_suggestion(room))

        return tuple(_dedupe_and_rank(suggestions, self.config.max_suggestions))


def mine_suggestions(
    activity: object,
    *,
    min_repetitions: int = MIN_PATTERN_REPETITIONS,
    max_suggestions: int = DEFAULT_MAX_SUGGESTIONS,
    cluster_window: int = DEFAULT_CLUSTER_WINDOW,
) -> tuple[Suggestion, ...]:
    """Return review-only suggestions mined from already-consented local signals."""

    return SuggestionMiner(
        PatternMinerConfig(
            min_repetitions=min_repetitions,
            max_suggestions=max_suggestions,
            cluster_window=cluster_window,
        )
    ).mine(activity)


def _observations_from_activity(activity: object) -> Iterable[_Observation]:
    position = 0
    for signal_id, raw_signal in enumerate(_iter_raw_signals(activity)):
        signal = _signal_mapping(raw_signal)
        if signal is None:
            continue
        source_id = normalize_activity_id(signal.get("source_id"))
        if source_id not in ALLOWED_ACTIVITY_SOURCE_IDS:
            continue
        if source_id in _normalized_forbidden_sources():
            continue

        metadata, metadata_risk = _metadata(signal)
        if metadata is None:
            continue
        if normalize_activity_id(metadata.get("room_id")) in _INTERNAL_ROOM_IDS:
            continue
        context_id = _context_id(metadata)
        for observation in _extract_observations(signal, metadata, metadata_risk):
            yield _Observation(
                category=observation.category,
                key=observation.key,
                label=observation.label,
                source_id=source_id,
                position=position,
                signal_id=signal_id,
                context_id=context_id,
                risk=observation.risk,
            )
            position += 1


def _iter_raw_signals(activity: object) -> Iterable[object]:
    if isinstance(activity, ActivityCollectionResult):
        yield from activity.signals
        return
    if isinstance(activity, ActivitySignal):
        yield activity
        return
    if isinstance(activity, Mapping):
        yield activity
        return
    if isinstance(activity, Iterable) and not isinstance(activity, str | bytes):
        yield from activity


def _signal_mapping(raw_signal: object) -> dict[str, object] | None:
    if isinstance(raw_signal, ActivitySignal):
        return {
            "kind": raw_signal.kind,
            "source_id": raw_signal.source_id,
            "label": raw_signal.label,
            "value": raw_signal.value,
            "metadata": dict(raw_signal.metadata),
        }
    if not isinstance(raw_signal, Mapping):
        return None

    if "event_type" in raw_signal or "payload" in raw_signal:
        payload = raw_signal.get("payload")
        metadata = dict(payload) if isinstance(payload, Mapping) else {}
        event_type = _clean_text(raw_signal.get("event_type"))
        if event_type:
            metadata["event_type"] = event_type
        return {
            "kind": "journal_event",
            "source_id": raw_signal.get("source_id") or RITUALIST_JOURNAL_SOURCE_ID,
            "label": raw_signal.get("label") or _journal_label(metadata),
            "value": event_type,
            "metadata": metadata,
        }

    return {
        "kind": raw_signal.get("kind") or "",
        "source_id": raw_signal.get("source_id") or "",
        "label": raw_signal.get("label") or "",
        "value": raw_signal.get("value") or "",
        "metadata": (
            raw_signal.get("metadata") if isinstance(raw_signal.get("metadata"), Mapping) else {}
        ),
    }


def _metadata(signal: Mapping[str, object]) -> tuple[dict[str, object], int] | tuple[None, int]:
    raw = signal.get("metadata")
    metadata = dict(raw) if isinstance(raw, Mapping) else {}
    cleaned: dict[str, object] = {}
    risk = 0
    for key, value in metadata.items():
        normalized_key = normalize_activity_id(key)
        if not normalized_key:
            continue
        if _forbidden_metadata_key(normalized_key):
            return None, 0
        if normalized_key in {"url", "uri", "href", "link"}:
            return None, 0
        cleaned[normalized_key] = value
        if normalized_key in {"domain", "domain_label", "host", "site", "url_domain"}:
            risk += 1
    return cleaned, risk


def _extract_observations(
    signal: Mapping[str, object],
    metadata: Mapping[str, object],
    metadata_risk: int,
) -> Iterable[_Observation]:
    kind = normalize_activity_id(signal.get("kind"))
    source_id = normalize_activity_id(signal.get("source_id"))
    label = signal.get("label")
    value = signal.get("value")

    if source_id == RECENT_ITEMS_SOURCE_ID and kind == "recent_reference":
        reference_type = normalize_activity_id(metadata.get("reference_type"))
        if reference_type == "folder":
            yield from _observation(
                "folder",
                label or metadata.get("target") or value,
                metadata_risk,
            )
        elif reference_type == "app":
            yield from _observation("app", label or metadata.get("target") or value, metadata_risk)
        return

    if source_id == OPEN_WINDOWS_SOURCE_ID:
        app_value = (
            metadata.get("app_name")
            or metadata.get("process_name")
            or (label if kind == "process_name" else "")
            or value
        )
        yield from _observation("app", app_value, metadata_risk)
        return

    event_type = normalize_activity_id(metadata.get("event_type") or value)
    if source_id != RITUALIST_JOURNAL_SOURCE_ID and not event_type:
        return

    if event_type == "room_opened" or metadata.get("room_id"):
        yield from _observation("room", metadata.get("room_id"), metadata_risk)
    if event_type in {
        "recipe_run_started",
        "recipe_run_finished",
        "recipe_doctor_run",
        "recipe_dry_run",
    }:
        yield from _observation(
            "ritual",
            metadata.get("recipe_name") or metadata.get("recipe_id") or label,
            metadata_risk,
        )
    if event_type == "shortcut_opened" or metadata.get("shortcut_id"):
        yield from _observation("shortcut", metadata.get("shortcut_id") or label, metadata_risk)
    if event_type == "component_clicked" and metadata.get("component_id"):
        yield from _observation("shortcut", metadata.get("component_id"), metadata_risk + 1)

    yield from _first_matching_observation(
        "folder",
        metadata,
        ("folder_label", "folder_name", "folder", "directory_label", "path_label"),
        metadata_risk,
    )
    yield from _first_matching_observation(
        "app",
        metadata,
        ("app_label", "app_name", "process_name", "application"),
        metadata_risk,
    )
    yield from _first_matching_observation(
        "domain",
        metadata,
        ("domain_label", "domain", "url_domain", "host", "site"),
        metadata_risk,
    )


def _first_matching_observation(
    category: str,
    metadata: Mapping[str, object],
    keys: Sequence[str],
    risk: int,
) -> Iterable[_Observation]:
    for key in keys:
        if metadata.get(key):
            yield from _observation(category, metadata.get(key), risk)
            return


def _observation(category: str, raw_label: object, risk: int) -> Iterable[_Observation]:
    normalized = _safe_observation_label(category, raw_label)
    if normalized is None:
        return
    key, label, label_risk = normalized
    if category == "room" and key in _INTERNAL_ROOM_IDS:
        return
    yield _Observation(
        category=category,
        key=key,
        label=label,
        source_id="",
        position=0,
        signal_id=0,
        risk=risk + label_risk,
    )


def _safe_observation_label(category: str, raw_label: object) -> tuple[str, str, int] | None:
    if isinstance(raw_label, bytes | bytearray):
        return None
    if isinstance(raw_label, Mapping):
        return None
    if isinstance(raw_label, Sequence) and not isinstance(raw_label, str | bytes | bytearray):
        return None
    text = _clean_text(raw_label)
    if not text:
        return None
    normalized = normalize_activity_id(text)
    if any(token in normalized for token in _FORBIDDEN_LABEL_TOKENS):
        return None
    if any(token in normalized for token in _SENSITIVE_LABEL_TOKENS):
        return None
    if _HTML_OR_SCRIPT_MARKER_RE.search(text):
        return None
    if _contains_non_http_uri_scheme(text):
        return None

    risk = 0
    if category == "domain":
        domain = _domain_from_text(text)
        if not domain:
            return None
        return domain, _domain_display_label(domain), risk + 1

    if _looks_like_url(text):
        if category != "domain":
            return None
        domain = _domain_from_text(text)
        if not domain:
            return None
        return domain, _domain_display_label(domain), risk + 2
    if category != "domain" and _looks_like_malformed_bracketed_locator(text):
        return None
    if category != "domain" and _looks_like_schemeless_url(text):
        return None
    if category != "domain" and _has_uri_scheme(text):
        return None
    if category != "domain" and _looks_like_protocol_relative_url(text):
        return None

    if _looks_like_path(text):
        text = _basename(text) or "local item"
        risk += 1

    if category == "app":
        text = _strip_executable_suffix(text)

    if category == "room":
        room_key = normalize_activity_id(text)
        if room_key in _PROMOTED_ROOM_NAMES:
            return room_key, _PROMOTED_ROOM_NAMES[room_key], risk

    label = _display_label(text, category)
    if not label:
        return None
    return normalize_activity_id(label), label, risk


def _aggregate_observations(
    observations: Sequence[_Observation],
) -> dict[tuple[str, str], _Aggregate]:
    aggregates: dict[tuple[str, str], _Aggregate] = {}
    for observation in observations:
        key = (observation.category, observation.key)
        aggregate = aggregates.get(key)
        if aggregate is None:
            aggregate = _Aggregate(
                category=observation.category,
                key=observation.key,
                label=observation.label,
                sources=set(),
            )
            aggregates[key] = aggregate
        aggregate.add(observation)
    return aggregates


def _ranked_singles(
    aggregates: Mapping[tuple[str, str], _Aggregate],
    min_repetitions: int,
) -> Iterable[_Aggregate]:
    for aggregate in sorted(
        aggregates.values(),
        key=lambda item: (-item.count, item.category, item.label.casefold()),
    ):
        if aggregate.category not in {"folder", "app", "domain"}:
            continue
        if aggregate.count >= min_repetitions:
            yield aggregate


def _ranked_pairs(
    observations: Sequence[_Observation],
    aggregates: Mapping[tuple[str, str], _Aggregate],
    *,
    min_repetitions: int,
    cluster_window: int,
) -> Iterable[_PairAggregate]:
    counts: Counter[tuple[str, str, str, str]] = Counter()
    risks: Counter[tuple[str, str, str, str]] = Counter()
    sources: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)

    for group in _coherent_groups(observations, cluster_window):
        seen_in_group: set[tuple[str, str, str, str]] = set()
        for left_category, right_category in _PAIR_CATEGORIES:
            left_items = {item.key: item for item in group if item.category == left_category}
            right_items = {item.key: item for item in group if item.category == right_category}
            for left in left_items.values():
                for right in right_items.values():
                    key = (left.category, left.key, right.category, right.key)
                    if key in seen_in_group:
                        continue
                    seen_in_group.add(key)
                    counts[key] += 1
                    risks[key] += left.risk + right.risk
                    sources[key].update((left.source_id, right.source_id))

    ranked_keys = sorted(
        (key for key, count in counts.items() if count >= min_repetitions),
        key=lambda key: (-counts[key], key),
    )
    for key in ranked_keys:
        left = aggregates.get((key[0], key[1]))
        right = aggregates.get((key[2], key[3]))
        if left is None or right is None:
            continue
        yield _PairAggregate(
            left=left,
            right=right,
            count=counts[key],
            risk=risks[key],
            sources=tuple(sorted(source for source in sources[key] if source)),
        )


def _coherent_groups(
    observations: Sequence[_Observation],
    cluster_window: int,
) -> Iterable[tuple[_Observation, ...]]:
    by_signal: dict[int, list[_Observation]] = defaultdict(list)
    by_context: dict[str, list[_Observation]] = defaultdict(list)
    for observation in observations:
        by_signal[observation.signal_id].append(observation)
        if observation.context_id:
            by_context[observation.context_id].append(observation)

    yielded: set[tuple[int, ...]] = set()
    for group in tuple(by_signal.values()) + tuple(by_context.values()):
        if len(group) < 2:
            continue
        key = tuple(sorted(item.position for item in group))
        if key in yielded:
            continue
        yielded.add(key)
        yield tuple(group)

    if not observations:
        return
    for start in range(len(observations)):
        group = tuple(observations[start : start + cluster_window])
        if len(group) < 2:
            continue
        key = tuple(item.position for item in group)
        if key in yielded:
            continue
        yielded.add(key)
        yield group


def _ranked_room_clusters(
    observations: Sequence[_Observation],
    aggregates: Mapping[tuple[str, str], _Aggregate],
    *,
    min_repetitions: int,
    cluster_window: int,
) -> Iterable[_PairAggregate]:
    support: dict[str, Counter[str]] = defaultdict(Counter)
    risks: Counter[str] = Counter()
    sources: dict[str, set[str]] = defaultdict(set)
    for group in _coherent_groups(observations, cluster_window):
        rooms = {item.key: item for item in group if item.category == "room"}
        if not rooms:
            continue
        supporting_categories = {item.category for item in group if item.category != "room"}
        for room_key, room in rooms.items():
            for category in supporting_categories:
                support[room_key][category] += 1
            risks[room_key] += sum(item.risk for item in group)
            sources[room_key].update(item.source_id for item in group if item.source_id)

    ranked = sorted(
        (
            room
            for room in (
                aggregate for aggregate in aggregates.values() if aggregate.category == "room"
            )
            if room.count >= min_repetitions
            and room.key not in _INTERNAL_ROOM_IDS
            and len(support.get(room.key, ())) >= 2
        ),
        key=lambda item: (-item.count, item.label.casefold()),
    )
    for room in ranked:
        yield _PairAggregate(
            left=room,
            right=_Aggregate(
                category="support",
                key=",".join(sorted(support[room.key])),
                label=", ".join(sorted(support[room.key])),
                count=sum(support[room.key].values()),
                risk=risks[room.key],
                sources=sources[room.key],
            ),
            count=room.count,
            risk=risks[room.key] + room.risk,
            sources=tuple(sorted(sources[room.key] or set(room.source_tuple))),
        )


def _single_suggestion(aggregate: _Aggregate, min_repetitions: int) -> Suggestion | None:
    if aggregate.category == "folder":
        component_type = "shortcut.folder"
        missing_inputs = ("folder_path",)
    elif aggregate.category == "app":
        component_type = "shortcut.app"
        missing_inputs = ("app_target",)
    elif aggregate.category == "domain":
        component_type = "shortcut.url"
        missing_inputs = ("url",)
    else:
        return None

    privacy_level = _privacy_level(aggregate.risk, default=SuggestionPrivacyLevel.LOW)
    return Suggestion(
        id=_suggestion_id("shortcut", aggregate.category, aggregate.key),
        kind=SuggestionKind.SHORTCUT_COMPONENT,
        title=f"Review {aggregate.label} shortcut",
        description=f"Repeated {aggregate.category} use can be reviewed as a shortcut component.",
        confidence=_confidence(aggregate.count, aggregate.risk, min_repetitions),
        evidence_summary=_evidence_summary(
            aggregate.category,
            aggregate.count,
            aggregate.source_tuple,
        ),
        evidence_count=aggregate.count,
        sources=aggregate.source_tuple,
        proposed_actions=(
            {
                "action": "review_shortcut_component",
                "kind": component_type,
                "component_type": component_type,
                "label": aggregate.label,
                "missing_input": missing_inputs[0],
            },
        ),
        missing_inputs=missing_inputs,
        privacy_level=privacy_level,
    )


def _pair_suggestion(pair: _PairAggregate, min_repetitions: int) -> Suggestion:
    left = pair.left
    right = pair.right
    category_label = f"{left.category} and {right.category}"
    title = f"Review {left.label} + {right.label} ritual"
    return Suggestion(
        id=_suggestion_id("ritual", left.category, left.key, right.category, right.key),
        kind=SuggestionKind.RITUAL_RECIPE,
        title=title,
        description=f"Repeated {category_label} co-use can be reviewed as a ritual recipe.",
        confidence=_confidence(pair.count, pair.risk, min_repetitions),
        evidence_summary=_cluster_evidence_summary(category_label, pair.count, pair.sources),
        evidence_count=pair.count,
        sources=pair.sources,
        proposed_actions=(
            {
                "action": "review_ritual_recipe",
                "kind": "ritual_recipe",
                "label": title,
                "description": "Review only ritual recipe suggestion; no recipe is created.",
                "missing_input": "recipe_review",
            },
        ),
        missing_inputs=("recipe_review",),
        privacy_level=_privacy_level(pair.risk),
    )


def _room_suggestion(room: _PairAggregate) -> Suggestion:
    source_tuple = room.sources or room.left.source_tuple
    return Suggestion(
        id=_suggestion_id("room", room.left.key, room.right.key),
        kind=SuggestionKind.ROOM_CANVAS,
        title=f"Review {room.left.label} canvas",
        description=(
            "Repeated Room use with related local activity can be reviewed as a "
            "Room canvas adjustment."
        ),
        confidence=_confidence(room.count, room.risk, MIN_PATTERN_REPETITIONS, ceiling=0.78),
        evidence_summary=_cluster_evidence_summary(
            "room usage with related local activity",
            room.count,
            source_tuple,
        ),
        evidence_count=room.count,
        sources=source_tuple,
        proposed_actions=(
            {
                "action": "review_room_canvas",
                "kind": "room_canvas",
                "room_id": room.left.key,
                "label": room.left.label,
                "description": "Review only Room canvas suggestion; no Room is created.",
            },
        ),
        missing_inputs=("room_review",),
        privacy_level=_privacy_level(room.risk),
    )


def _dedupe_and_rank(suggestions: Sequence[Suggestion], limit: int) -> list[Suggestion]:
    by_id: dict[str, Suggestion] = {}
    for suggestion in suggestions:
        existing = by_id.get(suggestion.id)
        if existing is None or suggestion.confidence > existing.confidence:
            by_id[suggestion.id] = suggestion
    ranked = sorted(
        by_id.values(),
        key=lambda item: (
            _kind_rank(item.kind),
            -item.confidence,
            -item.evidence_count,
            item.title.casefold(),
        ),
    )
    return ranked[:limit]


def _kind_rank(kind: SuggestionKind) -> int:
    if kind is SuggestionKind.ROOM_CANVAS:
        return 0
    if kind is SuggestionKind.RITUAL_RECIPE:
        return 1
    return 2


def _confidence(
    count: int,
    risk: int,
    min_repetitions: int,
    *,
    ceiling: float = 0.9,
) -> float:
    extra = max(0, count - min_repetitions)
    confidence = 0.58 + (0.08 * extra) - min(0.28, 0.05 * risk)
    return round(max(0.25, min(ceiling, confidence)), 2)


def _privacy_level(
    risk: int,
    *,
    default: SuggestionPrivacyLevel = SuggestionPrivacyLevel.REVIEW,
) -> SuggestionPrivacyLevel:
    if risk >= 4:
        return SuggestionPrivacyLevel.SENSITIVE
    if risk:
        return SuggestionPrivacyLevel.REVIEW
    return default


def _evidence_summary(category: str, count: int, sources: Sequence[str]) -> str:
    return f"Observed repeated {category} use {count} times from {_source_summary(sources)}."


def _cluster_evidence_summary(category_label: str, count: int, sources: Sequence[str]) -> str:
    return (
        f"Observed repeated {category_label} co-use {count} times from "
        f"{_source_summary(sources)}."
    )


def _source_summary(sources: Sequence[str]) -> str:
    if not sources:
        return "allowed local sources"
    return " and ".join(source.replace("_", " ") for source in sources)


def _suggestion_id(*parts: object) -> str:
    digest = hashlib.sha256(
        "|".join(_clean_text(part) for part in parts).encode("utf-8")
    ).hexdigest()
    return f"miner.{digest[:24]}"


def _context_id(metadata: Mapping[str, object]) -> str:
    for key in ("context_id", "session_id", "run_id", "room_id"):
        value = _clean_text(metadata.get(key))
        if value:
            return f"{key}:{normalize_activity_id(value)}"
    return ""


def _journal_label(metadata: Mapping[str, object]) -> str:
    for key in ("recipe_name", "recipe_id", "shortcut_id", "room_id", "component_id"):
        value = _clean_text(metadata.get(key))
        if value:
            return value
    return _clean_text(metadata.get("event_type"))


def _forbidden_metadata_key(normalized_key: str) -> bool:
    if normalized_key in FORBIDDEN_ACTIVITY_METADATA_KEYS:
        return True
    return any(token in normalized_key for token in FORBIDDEN_ACTIVITY_METADATA_KEY_TOKENS)


def _normalized_forbidden_sources() -> frozenset[str]:
    return frozenset(
        normalize_activity_id(source_id) for source_id in FORBIDDEN_ACTIVITY_SOURCE_IDS
    )


def _clean_text(value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())[:200]


def _display_label(text: str, category: str) -> str:
    label = _strip_executable_suffix(text.strip(" ."))
    label = label.replace("_", " ").replace("-", " ")
    label = " ".join(label.split())
    if not label:
        return ""
    if category in {"ritual", "shortcut", "room"}:
        return label[:80]
    return label[:60]


def _strip_executable_suffix(text: str) -> str:
    basename = _basename(text)
    suffix = ""
    if "." in basename:
        suffix = "." + basename.rsplit(".", 1)[-1].casefold()
    if suffix in _EXECUTABLE_SUFFIXES:
        return basename[: -len(suffix)]
    return text


def _basename(text: str) -> str:
    return text.rstrip("\\/").replace("\\", "/").rsplit("/", 1)[-1]


def _looks_like_path(text: str) -> bool:
    return bool(_PATH_RE.search(text))


def _looks_like_url(text: str) -> bool:
    try:
        parsed = urlparse(text)
    except ValueError:
        return False
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)


def _looks_like_schemeless_url(text: str) -> bool:
    normalized = text.casefold().replace("\\", "/")
    if (
        normalized == "localhost"
        or normalized.startswith("localhost/")
        or normalized.startswith("localhost:")
        or normalized.startswith("localhost?")
        or normalized.startswith("localhost#")
    ):
        return True
    if _looks_like_bare_dotted_host(normalized):
        return True
    if _looks_like_ipv4_locator(normalized):
        return True
    if _looks_like_bracketed_ipv6_locator(normalized):
        return True
    if _looks_like_unbracketed_ipv6_locator(normalized):
        return True
    if not (
        normalized.startswith("www.")
        or normalized.startswith("localhost/")
        or normalized.startswith("localhost:")
        or normalized.startswith("localhost?")
        or normalized.startswith("localhost#")
        or normalized.startswith("[")
        or "/" in normalized
        or "?" in normalized
        or "#" in normalized
    ):
        return False
    return bool(_domain_from_text(normalized))


def _looks_like_bare_dotted_host(text: str) -> bool:
    candidate = text.strip().strip(".")
    if (
        not candidate
        or any(separator in candidate for separator in ("/", "\\", "?", "#", ":"))
        or " " in candidate
        or "." not in candidate
    ):
        return False
    if _has_executable_suffix(candidate):
        return False
    return bool(_DOMAIN_RE.fullmatch(candidate))


def _looks_like_ipv4_locator(text: str) -> bool:
    candidate = text.strip()
    return bool(_IPV4_LOCATOR_RE.fullmatch(candidate))


def _looks_like_bracketed_ipv6_locator(text: str) -> bool:
    candidate = text.strip().replace("\\", "/")
    if not candidate.startswith("["):
        return False
    end = candidate.find("]")
    if end <= 1:
        return False
    rest = candidate[end + 1 :]
    if rest and not (rest.startswith(":") or rest.startswith("/") or rest.startswith("?") or rest.startswith("#")):
        return False
    try:
        return ipaddress.ip_address(candidate[1:end]).version == 6
    except ValueError:
        return False


def _looks_like_malformed_bracketed_locator(text: str) -> bool:
    candidate = text.strip().replace("\\", "/")
    if not candidate.startswith("["):
        return False
    end = candidate.find("]")
    if end <= 1 or _looks_like_bracketed_ipv6_locator(candidate):
        return False
    inner = candidate[1:end]
    rest = candidate[end + 1 :]
    return bool(
        rest.startswith(("/", "?", "#", ":"))
        or "://" in inner
        or ":" in inner
        or "@" in inner
        or "." in inner
    )


def _looks_like_unbracketed_ipv6_locator(text: str) -> bool:
    candidate = text.strip().replace("\\", "/")
    if not candidate or candidate.startswith("[") or ":" not in candidate:
        return False
    host = candidate.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    try:
        return ipaddress.ip_address(host).version == 6
    except ValueError:
        return False


def _has_executable_suffix(text: str) -> bool:
    basename = _basename(text)
    if "." not in basename:
        return False
    suffix = "." + basename.rsplit(".", 1)[-1].casefold()
    return suffix in _EXECUTABLE_SUFFIXES


def _has_uri_scheme(text: str) -> bool:
    if _WINDOWS_DRIVE_PATH_RE.match(text):
        return False
    return bool(_URI_SCHEME_RE.match(text))


def _contains_non_http_uri_scheme(text: str) -> bool:
    return any(
        _uri_scheme_token_should_reject(match)
        for match in _URI_SCHEME_TOKEN_RE.finditer(text)
    )


def _uri_scheme_token_should_reject(match: re.Match[str]) -> bool:
    scheme = match.group(1).casefold()
    if scheme in {"http", "https"}:
        return False
    if _WINDOWS_DRIVE_PATH_RE.match(match.group(0)):
        return False
    return True


def _looks_like_protocol_relative_url(text: str) -> bool:
    return bool(_PROTOCOL_RELATIVE_URL_RE.match(text))


def _domain_from_text(text: str) -> str:
    candidate = text.replace("\\", "/")
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return ""
    if parsed.scheme.casefold() in {"http", "https"} and parsed.netloc:
        host = parsed.netloc
    elif _DOMAIN_RE.match(candidate):
        host = candidate.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    elif (
        any(marker in candidate for marker in ("/", "?", "#"))
        or candidate.startswith("www.")
        or candidate.casefold().startswith("localhost:")
        or candidate.startswith("[")
    ):
        try:
            parsed = urlparse(f"https://{candidate}")
            hostname = parsed.hostname or ""
        except ValueError:
            return ""
        if not parsed.netloc or (
            "." not in hostname and ":" not in hostname and hostname != "localhost"
        ):
            return ""
        host = parsed.netloc
    else:
        return ""
    raw_host = host.rsplit("@", 1)[-1]
    if raw_host.startswith("["):
        end = raw_host.find("]")
        host = raw_host[1:end] if end > 0 else raw_host
    else:
        host = raw_host.split(":", 1)[0]
    host = host.strip(".").casefold()
    if host.startswith("www."):
        host = host[4:]
    if _looks_like_ip_host(host):
        return ""
    if "." not in host:
        return ""
    if not host or any(token in normalize_activity_id(host) for token in _SENSITIVE_LABEL_TOKENS):
        return ""
    return host


def _looks_like_ip_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _domain_display_label(domain: str) -> str:
    parts = [part for part in domain.split(".") if part]
    if not parts:
        return "web domain"
    useful = parts[:-1] if len(parts) > 1 else parts
    return " ".join(part.replace("-", " ") for part in useful[:3]) + " domain"


__all__ = [
    "DEFAULT_CLUSTER_WINDOW",
    "DEFAULT_MAX_SUGGESTIONS",
    "MIN_PATTERN_REPETITIONS",
    "PatternMinerConfig",
    "SuggestionMiner",
    "mine_suggestions",
]
