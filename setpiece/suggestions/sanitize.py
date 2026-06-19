from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import ipaddress
import re
from urllib.parse import urlsplit


REDACTED = "[redacted]"
HISTORY_OMITTED = "[history omitted]"
MAX_LABEL_LENGTH = 120
MAX_SUMMARY_LENGTH = 280
MAX_RAW_TEXT_LENGTH = 2_000
MAX_EVIDENCE_ITEMS = 20

URL_RE = re.compile(r"\bhttps?://[^\s<>'\"`]+", re.IGNORECASE)
DATA_URI_RE = re.compile(r"(?<![\w:])data:[^\s]+", re.IGNORECASE)
GENERIC_URI_RE = re.compile(
    r"(?<![\w:])(?:\[)?([A-Za-z][A-Za-z0-9+.-]*):"
    r"(?://[^\s<>'\"`\]]+|[^\s<>'\"`\]]+)(?:\])?"
)
HTML_OR_SCRIPT_MARKER_RE = re.compile(
    r"<\s*/?\s*[A-Za-z][^>]*>"
    r"|\bon[A-Za-z]+\s*="
    r"|\bjavascript\b"
    r"|\balert\s*\(",
    re.IGNORECASE,
)
SCHEMELESS_URL_RE = re.compile(
    r"(?<![@\w])localhost(?::\d{1,5})?(?:[\\/?#][^\s<>'\"`,;]*)?"
    r"|(?<![@\w])\[[0-9A-Fa-f:.]+(?:%[0-9A-Za-z_.~-]+)?\]"
    r"(?::\d{1,5})?(?:[\\/?#][^\s<>'\"`,;]*)?"
    r"|(?<![@\w])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?:[\\/?#][^\s<>'\"`,;]*)?"
    r"|(?<![@\w])(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
    r"(?::\d{1,5})?(?:[\\/?#][^\s<>'\"`,;]*)"
    r"|(?<![@\w])www\.[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
    r"(?::\d{1,5})?(?!\w)",
    re.IGNORECASE,
)
BARE_DOTTED_HOST_RE = re.compile(
    r"(?<![@\w])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}(?::\d{1,5})?(?![\w-])",
    re.IGNORECASE,
)
UNBRACKETED_IPV6_CANDIDATE_RE = re.compile(
    r"(?<![\w\[])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f]{0,4}"
    r"(?:%[0-9A-Za-z_.~-]+)?"
    r"(?:[\\/?#][^\s<>'\"`,;]*)?",
    re.IGNORECASE,
)
PROTOCOL_RELATIVE_URL_RE = re.compile(
    r"(?<![:\w])//(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
    r"(?::\d{1,5})?(?:/[^\s<>'\"`,;]*)?",
    re.IGNORECASE,
)
WINDOWS_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![\w@])(?:"
    r"[A-Za-z]:[\\/](?:[^\s<>:\"|?*,;\r\n]+[\\/]?)*[^\s<>:\"|?*,;\r\n]+"
    r"|\\\\[^\\/\s]+[\\/][^\\/\s]+(?:[\\/][^\s<>:\"|?*,;\r\n]+)*"
    r")"
)
POSIX_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![\w:/.-])/"
    r"(?:Users|home|var|tmp|etc|opt|srv|mnt|Volumes|Applications|ProgramData|"
    r"Program Files|Windows|workspace|private|run|usr)"
    r"(?:/[^\s,;|<>\"'`]+)*",
    re.IGNORECASE,
)
TOKEN_OR_CREDENTIAL_RE = re.compile(
    r"("
    r"\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|auth[_ -]?token|"
    r"id[_ -]?token|client[_ -]?secret|token|password|passwd|pwd|credentials?|"
    r"private[_ -]?key)\b\s*[:=]"
    r"|://[^/\s:@]+:[^/\s@]+@"
    r"|\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*"
    r"|\b(?:gh[pousr]_|xox[baprs]-)[A-Za-z0-9_-]{16,}\b"
    r"|\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}\b"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    r")",
    re.IGNORECASE,
)
SENSITIVE_LABEL_RE = re.compile(
    r"\b(?:api[_ -]?keys?|credentials?|passwords?|private[_ -]?keys?|secrets?|tokens?)\b",
    re.IGNORECASE,
)
SENSITIVE_PATH_MARKER_RE = re.compile(
    r"\b(?:credential|keychain|password|private|secret|token|vault)\b",
    re.IGNORECASE,
)
PRIVATE_CONTEXT_RE = re.compile(
    r"\b(?:incognito|inprivate|private\s+(?:browsing|mode|tab|window)|"
    r"off[- ]the[- ]record)\b",
    re.IGNORECASE,
)
FORBIDDEN_COLLECTION_MARKER_RE = re.compile(
    r"\b(?:browser[-_\s]?history|click\s+coordinates?|coordinate\s+capture|"
    r"coordinates?\s+\d+\s*,\s*\d+|key\s*[-_ ]?\s*log(?:ger|ging)?|"
    r"keyboard[-_\s]?logger|keylog(?:ger|ging)?|ocr|raw\s+history|recall|"
    r"recorder|recording|"
    r"screen[-_\s]+capture|screencapture|screen[-_\s]+recorder|screenrecorder|"
    r"screen[-_\s]+recording|screenshots?|teach[-_\s]+by[-_\s]+watching|"
    r"teachbywatching|watch[-_\s]?me|windows[-_\s]+recall|windowsrecall)\b",
    re.IGNORECASE,
)
EMAIL_HEADER_RE = re.compile(r"(?im)^\s*(?:from|to|cc|bcc|subject|sent|date):\s+\S")
MESSAGE_BODY_RE = re.compile(
    r"\b(?:chat|conversation|dm|email|message|sms)\s+"
    r"(?:body|contents?|thread|transcript)\b"
    r"|(?:^|\n)\s*on .{0,120}\bwrote:\s*$",
    re.IGNORECASE,
)
RAW_HISTORY_KEY_RE = re.compile(
    r"\b(?:activity|browser_history|events?|history|log|raw|timeline)\b",
    re.IGNORECASE,
)
RAW_HISTORY_KEY_TOKENS = frozenset(
    {"activity", "browser_history", "event", "events", "history", "log", "raw", "timeline"}
)
FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "body",
        "browser_history",
        "browserhistory",
        "coordinate",
        "coordinates",
        "click_coordinate",
        "click_coordinates",
        "content",
        "coordinate_capture",
        "credential",
        "credentials",
        "email",
        "keylog",
        "keylogger",
        "keylogging",
        "keyboard_logger",
        "keyboardlogger",
        "message",
        "ocr",
        "password",
        "recall",
        "recorder",
        "recording",
        "screen_capture",
        "screen_recorder",
        "screenrecorder",
        "screencapture",
        "screen_recording",
        "screenshot",
        "teach_by_watching",
        "teachbywatching",
        "token",
        "watch_me",
        "windows_recall",
        "windowsrecall",
    }
)
PATH_SEPARATOR_RE = re.compile(r"[\\/]+")
TRAILING_URL_PUNCTUATION = ".,;:!?)]}'\""
EXECUTABLE_SUFFIX_RE = re.compile(r"\.(?:app|bat|cmd|com|exe|msi|ps1|sh)$", re.IGNORECASE)
SWITCH_ARGUMENT_RE = re.compile(r"\s[-/][A-Za-z][\w-]*(?:\s|$)")
IPV4_HOST_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
WINDOWS_DRIVE_PATH_TOKEN_RE = re.compile(r"^[A-Za-z]:[\\/](?![\\/])")
LOCALHOST_PORT_TOKEN_RE = re.compile(r"^localhost:\d{1,5}(?:[\\/?#].*)?$", re.IGNORECASE)


def sanitize_url(value: object, *, title: object | None = None) -> str:
    """Return a safe domain label, optionally paired with a safe page title."""

    raw = _raw_text(value)
    if not raw:
        return ""
    if _must_redact(raw):
        return REDACTED
    candidate = _strip_url_punctuation(raw)
    parsed = urlsplit(candidate)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return REDACTED
    if parsed.username or parsed.password or _contains_private_context(raw):
        return REDACTED

    domain = _domain_label(parsed.hostname)
    if not domain:
        return REDACTED

    if title is None:
        return domain

    safe_title = _sanitize_public_text(title, max_length=MAX_LABEL_LENGTH)
    if safe_title == REDACTED or safe_title == HISTORY_OMITTED:
        return REDACTED
    if not safe_title or safe_title.casefold() == domain.casefold():
        return domain
    return f"{safe_title} ({domain})"


def sanitize_local_path(value: object) -> str:
    """Reduce a local path string to the final useful label without ancestors."""

    raw = _raw_text(value)
    if not raw:
        return ""
    if (
        URL_RE.search(raw)
        or _contains_non_http_uri_scheme(raw)
        or PROTOCOL_RELATIVE_URL_RE.search(raw)
        or SCHEMELESS_URL_RE.search(raw)
        or _contains_unbracketed_ipv6_locator(raw)
        or (
            _contains_bare_dotted_host(raw)
            and "\\" not in raw
            and "/" not in raw
        )
        or _must_redact(raw)
    ):
        return REDACTED

    text = raw.strip().strip("'\"`")
    text = text.rstrip("\\/")
    if not text:
        return ""

    normalized = text.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part and not re.fullmatch(r"[A-Za-z]:", part)]
    if not parts:
        return "local drive"

    lower_parts = [part.casefold() for part in parts]
    if _is_user_profile_root(lower_parts):
        return "user folder"
    if normalized.startswith("//") and len(parts) <= 2:
        return "network share"
    if any(_has_sensitive_path_marker(part) for part in parts):
        return REDACTED

    label = _clean_label(parts[-1], max_length=MAX_LABEL_LENGTH)
    if not label or label in {".", ".."}:
        return REDACTED
    if SENSITIVE_LABEL_RE.search(label) or _contains_private_context(label):
        return REDACTED
    return label


def sanitize_window_title(value: object) -> str:
    """Sanitize a window title that was supplied by a caller."""

    return _sanitize_public_text(value, max_length=MAX_LABEL_LENGTH)


def sanitize_app_name(value: object) -> str:
    """Sanitize an app or process label without preserving command arguments."""

    raw = _raw_text(value)
    if not raw:
        return ""
    if (
        _must_redact(raw)
        or URL_RE.search(raw)
        or _contains_non_http_uri_scheme(raw)
        or PROTOCOL_RELATIVE_URL_RE.search(raw)
        or SCHEMELESS_URL_RE.search(raw)
        or _contains_unbracketed_ipv6_locator(raw)
        or _contains_bare_dotted_host(raw)
    ):
        return REDACTED
    if SWITCH_ARGUMENT_RE.search(raw):
        return REDACTED

    label = sanitize_local_path(raw) if "\\" in raw or "/" in raw else _clean_label(raw)
    if label == REDACTED:
        return REDACTED
    label = EXECUTABLE_SUFFIX_RE.sub("", label)
    label = _clean_label(label, max_length=MAX_LABEL_LENGTH)
    if not label or SENSITIVE_LABEL_RE.search(label):
        return REDACTED
    return label


def sanitize_evidence_summary(value: object) -> str:
    """Sanitize caller-supplied evidence text or compact evidence records."""

    if _looks_like_huge_history(value):
        return HISTORY_OMITTED
    if isinstance(value, Mapping):
        return _sanitize_evidence_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        items = sanitize_evidence_items(value)
        return "; ".join(items)
    return _sanitize_public_text(value, max_length=MAX_SUMMARY_LENGTH)


def sanitize_evidence_items(
    values: Iterable[object],
    *,
    max_items: int = MAX_EVIDENCE_ITEMS,
) -> tuple[str, ...]:
    """Sanitize a bounded list of evidence labels."""

    items = list(values)
    if len(items) > max_items:
        return (HISTORY_OMITTED,)

    sanitized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = sanitize_evidence_summary(item)
        if not text:
            continue
        if text == HISTORY_OMITTED:
            return (HISTORY_OMITTED,)
        if text in seen:
            continue
        seen.add(text)
        sanitized.append(text)
    return tuple(sanitized)


def _sanitize_evidence_mapping(value: Mapping[object, object]) -> str:
    labels: list[str] = []
    for raw_key, item in list(value.items())[:MAX_EVIDENCE_ITEMS]:
        key = _clean_key(raw_key)
        if not key or _is_forbidden_key(key):
            continue
        if "url" in key or key in {"domain", "uri"}:
            label = sanitize_url(item)
        elif "path" in key or "folder" in key or "file" in key:
            label = sanitize_local_path(item)
        elif "window" in key or "title" in key:
            label = sanitize_window_title(item)
        elif "app" in key or "process" in key:
            label = sanitize_app_name(item)
        elif "evidence" in key or "summary" in key or "label" in key:
            label = sanitize_evidence_summary(item)
        else:
            continue
        if label and label not in labels:
            labels.append(label)
    return _truncate("; ".join(labels), max_length=MAX_SUMMARY_LENGTH)


def _sanitize_public_text(value: object, *, max_length: int) -> str:
    raw = _raw_text(value)
    if not raw:
        return ""
    if _looks_like_huge_history(raw):
        return HISTORY_OMITTED
    if _must_redact(raw):
        return REDACTED
    if DATA_URI_RE.search(raw):
        return REDACTED

    text = _clean_label(raw, max_length=MAX_RAW_TEXT_LENGTH)
    text = GENERIC_URI_RE.sub(lambda match: _sanitize_generic_uri(match), text)
    text = URL_RE.sub(lambda match: sanitize_url(match.group(0)), text)
    text = PROTOCOL_RELATIVE_URL_RE.sub(
        lambda match: _sanitize_protocol_relative_url(match.group(0)), text
    )
    text = SCHEMELESS_URL_RE.sub(lambda match: _sanitize_schemeless_url(match.group(0)), text)
    text = UNBRACKETED_IPV6_CANDIDATE_RE.sub(
        lambda match: _sanitize_unbracketed_ipv6_locator(match.group(0)),
        text,
    )
    text = BARE_DOTTED_HOST_RE.sub(
        lambda match: _sanitize_bare_dotted_host(match.group(0)),
        text,
    )
    text = WINDOWS_ABSOLUTE_PATH_RE.sub(lambda match: sanitize_local_path(match.group(0)), text)
    text = POSIX_ABSOLUTE_PATH_RE.sub(lambda match: sanitize_local_path(match.group(0)), text)
    if _must_redact(text):
        return REDACTED
    return _truncate(text, max_length=max_length)


def _must_redact(value: object) -> bool:
    raw = _raw_text(value)
    return bool(
        TOKEN_OR_CREDENTIAL_RE.search(raw)
        or HTML_OR_SCRIPT_MARKER_RE.search(raw)
        or SENSITIVE_LABEL_RE.search(raw)
        or _contains_private_context(raw)
        or FORBIDDEN_COLLECTION_MARKER_RE.search(raw)
        or _looks_like_message_body(raw)
    )


def _looks_like_message_body(raw: str) -> bool:
    if MESSAGE_BODY_RE.search(raw):
        return True
    if len(EMAIL_HEADER_RE.findall(raw)) >= 2:
        return True
    line_count = raw.count("\n") + raw.count("\r")
    if line_count >= 2 and re.search(r"\b(?:dear|regards|sent from my|subject:)\b", raw, re.IGNORECASE):
        return True
    return False


def _looks_like_huge_history(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _key_has_token(_clean_key(key), RAW_HISTORY_KEY_TOKENS):
                if isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
                    return len(item) > MAX_EVIDENCE_ITEMS
                text = _raw_text(item)
                if _raw_text_looks_like_huge_history(text):
                    return True
        return len(value) > MAX_EVIDENCE_ITEMS * 2
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return len(value) > MAX_EVIDENCE_ITEMS
    return _raw_text_looks_like_huge_history(_raw_text(value))


def _raw_text_looks_like_huge_history(raw: str) -> bool:
    if not raw:
        return False
    url_count = (
        len(URL_RE.findall(raw))
        + len(PROTOCOL_RELATIVE_URL_RE.findall(raw))
        + len(SCHEMELESS_URL_RE.findall(raw))
    )
    path_count = len(WINDOWS_ABSOLUTE_PATH_RE.findall(raw)) + len(POSIX_ABSOLUTE_PATH_RE.findall(raw))
    line_count = raw.count("\n") + raw.count("\r")
    if url_count > 8 or path_count > 8:
        return True
    if len(raw) > MAX_RAW_TEXT_LENGTH and (url_count + path_count > 3 or line_count > 8):
        return True
    if RAW_HISTORY_KEY_RE.search(raw) and (line_count > 8 or raw.count(";") > 20):
        return True
    return False


def _contains_private_context(raw: str) -> bool:
    return bool(PRIVATE_CONTEXT_RE.search(raw))


def _is_forbidden_key(key: str) -> bool:
    return bool(
        TOKEN_OR_CREDENTIAL_RE.search(f"{key}=")
        or _key_has_token(key, FORBIDDEN_KEY_TOKENS)
        or FORBIDDEN_COLLECTION_MARKER_RE.search(key.replace("_", " "))
    )


def _key_has_token(key: str, tokens: frozenset[str]) -> bool:
    parts = tuple(part for part in key.split("_") if part)
    return any(
        key == token
        or key.startswith(f"{token}_")
        or key.endswith(f"_{token}")
        or f"_{token}_" in key
        or token in parts
        for token in tokens
    )


def _is_user_profile_root(parts: Sequence[str]) -> bool:
    for marker in ("users", "home"):
        if marker in parts:
            index = parts.index(marker)
            return len(parts) == index + 2
    return False


def _has_sensitive_path_marker(part: str) -> bool:
    normalized = part.casefold().replace("-", "_").replace(" ", "_")
    return bool(
        SENSITIVE_PATH_MARKER_RE.search(part)
        or any(
            marker in normalized
            for marker in ("credential", "keychain", "password", "private", "secret", "token", "vault")
        )
    )


def _domain_label(hostname: str) -> str:
    host = hostname.strip(".").casefold()
    if host.startswith("www."):
        host = host[4:]
    if IPV4_HOST_RE.fullmatch(host) or _looks_like_ip_host(host):
        return ""
    if "." not in host:
        return ""
    if not re.fullmatch(r"[a-z0-9.-]{1,253}", host) or ".." in host:
        return ""
    return host


def _sanitize_schemeless_url(value: object) -> str:
    raw = _strip_url_punctuation(_raw_text(value)).replace("\\", "/")
    if not raw or _must_redact(raw):
        return REDACTED
    return sanitize_url(f"https://{raw}")


def _sanitize_bare_dotted_host(value: object) -> str:
    raw = _strip_url_punctuation(_raw_text(value))
    if _looks_like_executable_label(raw):
        return raw
    if not raw or _must_redact(raw):
        return REDACTED
    return sanitize_url(f"https://{raw}")


def _sanitize_unbracketed_ipv6_locator(value: object) -> str:
    raw = _strip_url_punctuation(_raw_text(value))
    if _looks_like_unbracketed_ipv6_locator(raw):
        return REDACTED
    return raw


def _sanitize_protocol_relative_url(value: object) -> str:
    raw = _strip_url_punctuation(_raw_text(value))
    if not raw or _must_redact(raw):
        return REDACTED
    return sanitize_url(f"https:{raw}")


def _strip_url_punctuation(value: str) -> str:
    return value.strip().rstrip(TRAILING_URL_PUNCTUATION)


def _contains_bare_dotted_host(value: object) -> bool:
    raw = _raw_text(value)
    return any(
        not _looks_like_executable_label(match.group(0))
        for match in BARE_DOTTED_HOST_RE.finditer(raw)
    )


def _contains_unbracketed_ipv6_locator(value: object) -> bool:
    return any(
        _looks_like_unbracketed_ipv6_locator(match.group(0))
        for match in UNBRACKETED_IPV6_CANDIDATE_RE.finditer(_raw_text(value))
    )


def _contains_non_http_uri_scheme(value: object) -> bool:
    return any(
        _generic_uri_should_redact(match)
        for match in GENERIC_URI_RE.finditer(_raw_text(value))
    )


def _sanitize_generic_uri(match: re.Match[str]) -> str:
    if not _generic_uri_should_redact(match):
        return match.group(0)
    return REDACTED


def _generic_uri_should_redact(match: re.Match[str]) -> bool:
    scheme = match.group(1).casefold()
    if scheme in {"http", "https"}:
        return False
    if _looks_like_bracketed_ip_uri_token(match.group(0)):
        return False
    if WINDOWS_DRIVE_PATH_TOKEN_RE.match(match.group(0)):
        return False
    if LOCALHOST_PORT_TOKEN_RE.match(match.group(0)):
        return False
    return True


def _looks_like_bracketed_ip_uri_token(value: object) -> bool:
    raw = _raw_text(value)
    if not raw.startswith("["):
        return False
    end = raw.find("]")
    if end <= 1:
        return False
    try:
        ipaddress.ip_address(raw[1:end])
        return True
    except ValueError:
        return False


def _looks_like_unbracketed_ipv6_locator(value: object) -> bool:
    raw = _strip_url_punctuation(_raw_text(value)).replace("\\", "/")
    if not raw or raw.startswith("[") or ":" not in raw:
        return False
    host = raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    try:
        return ipaddress.ip_address(host).version == 6
    except ValueError:
        return False


def _looks_like_ip_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _looks_like_executable_label(value: object) -> bool:
    raw = _strip_url_punctuation(_raw_text(value))
    if not raw or any(separator in raw for separator in ("/", "\\", "?", "#", ":")):
        return False
    return bool(EXECUTABLE_SUFFIX_RE.search(raw))


def _clean_key(value: object) -> str:
    return _clean_label(value, max_length=80).casefold().replace("-", "_").replace(" ", "_")


def _clean_label(value: object, *, max_length: int = MAX_LABEL_LENGTH) -> str:
    text = _raw_text(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return _truncate(" ".join(text.split()), max_length=max_length)


def _raw_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes | bytearray):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _truncate(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip() + "…"


__all__ = [
    "HISTORY_OMITTED",
    "MAX_EVIDENCE_ITEMS",
    "REDACTED",
    "sanitize_app_name",
    "sanitize_evidence_items",
    "sanitize_evidence_summary",
    "sanitize_local_path",
    "sanitize_url",
    "sanitize_window_title",
]
