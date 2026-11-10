"""
Shared helpers for converting simple values (string / number / bool / list) into
Notion API property values. Used by create_database_record and update_database_record.
"""

from datetime import date, datetime
from typing import Any
import json
import math
import re

# Notion caps each rich_text / title text object at 2000 characters (counted in UTF-16 code units)
# and a rich_text array at 100 elements
RICH_TEXT_CHUNK_SIZE = 2000
RICH_TEXT_MAX_ITEMS = 100

# Property types computed or managed by Notion; the API rejects writes to them
READ_ONLY_PROPERTY_TYPES = {
    "formula", "rollup", "unique_id", "verification", "button",
    "created_time", "created_by", "last_edited_time", "last_edited_by",
}

TRUE_STRINGS = {"true", "yes", "1"}
FALSE_STRINGS = {"false", "no", "0"}

# Notion stores numbers as IEEE 754 doubles, so integers beyond this cannot be represented exactly
MAX_SAFE_INTEGER = 2**53 - 1

INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")


class InvalidPropertyValueError(ValueError):
    """Raised when a supplied value cannot be written to, or matched against, a property."""


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def parse_bool(prop_name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = "" if value is None else str(value).strip().lower()
    if text in TRUE_STRINGS:
        return True
    if text in FALSE_STRINGS:
        return False
    raise InvalidPropertyValueError(f"Property '{prop_name}' (type: checkbox) requires true or false (got: {value!r}).")


def parse_number(prop_name: str, value: Any) -> int | float:
    """Parse a number without lossy conversion: integers (and integer strings) stay exact,
    and integers Notion cannot store exactly are rejected instead of being rounded."""
    invalid = InvalidPropertyValueError(f"Property '{prop_name}' (type: number) requires a numeric value (got: {value!r}).")
    if isinstance(value, bool):
        raise invalid
    if isinstance(value, str):
        text = value.strip()
        if INTEGER_PATTERN.match(text):
            value = int(text)
        else:
            try:
                value = float(text)
            except ValueError:
                raise invalid
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidPropertyValueError(f"Property '{prop_name}' (type: number) requires a finite number (got: {value!r}).")
        if not value.is_integer():
            return value
        if abs(value) > MAX_SAFE_INTEGER:
            raise InvalidPropertyValueError(
                f"Property '{prop_name}' (type: number) cannot store {value!r} exactly (integers must be within ±{MAX_SAFE_INTEGER})."
            )
        return int(value)
    if not isinstance(value, int):
        raise invalid
    if abs(value) > MAX_SAFE_INTEGER:
        raise InvalidPropertyValueError(
            f"Property '{prop_name}' (type: number) cannot store {value!r} exactly (integers must be within ±{MAX_SAFE_INTEGER})."
        )
    return value


def parse_date(prop_name: str, value: Any) -> dict:
    if isinstance(value, dict):
        if value.get("start") is None or (isinstance(value["start"], str) and not value["start"].strip()):
            raise InvalidPropertyValueError(f"Property '{prop_name}' (type: date) requires a 'start' value.")
        # Validate start / end as date strings and return a normalised copy (other keys such as time_zone are kept)
        result = dict(value)
        for key in ("start", "end"):
            if value.get(key) is None:
                continue
            if not isinstance(value[key], str):
                raise InvalidPropertyValueError(
                    f"Property '{prop_name}' (type: date) requires an ISO 8601 date string for '{key}' (got: {value[key]!r})."
                )
            result[key] = parse_date(prop_name, value[key])["start"]
        return result
    if not isinstance(value, str):
        raise InvalidPropertyValueError(
            f"Property '{prop_name}' (type: date) requires an ISO 8601 date string (got: {value!r})."
        )
    text = value.strip()
    try:
        if len(text) == 10:
            date.fromisoformat(text)
        else:
            datetime.fromisoformat(text)
    except ValueError:
        raise InvalidPropertyValueError(
            f"Property '{prop_name}' (type: date) requires an ISO 8601 date such as 2026-10-01 or 2026-10-01T09:00:00+09:00 (got: {value!r})."
        )
    return {"start": text}


def _parse_list(value: Any) -> list[str]:
    """Accept a list, a JSON array string, or a comma-separated string and return non-empty strings."""
    if is_empty(value):
        return []
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
    if not isinstance(value, list):
        value = str(value).split(",")
    return [str(item).strip() for item in value if not is_empty(item)]


def _parse_ids(prop_name: str, prop_type: str, value: Any) -> list[dict]:
    ids = _parse_list(value)
    invalid = [item for item in ids if not UUID_PATTERN.match(item)]
    if invalid:
        kind = "user" if prop_type == "people" else "page"
        raise InvalidPropertyValueError(
            f"Property '{prop_name}' (type: {prop_type}) requires Notion {kind} IDs (got: {', '.join(invalid)})."
        )
    return [{"id": item_id} for item_id in ids]


def _scalar_text(prop_name: str, prop_type: str, value: Any) -> str:
    if isinstance(value, (list, dict, bool)):
        raise InvalidPropertyValueError(f"Property '{prop_name}' (type: {prop_type}) requires a single text value (got: {value!r}).")
    return str(value).strip()


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def to_rich_text(prop_name: str, value: Any) -> list:
    if isinstance(value, (list, dict, bool)):
        raise InvalidPropertyValueError(f"Property '{prop_name}' requires a text value (got: {value!r}).")
    text = "" if value is None else str(value)
    chunks, current, current_len = [], [], 0
    for char in text:
        char_len = _utf16_len(char)
        if current_len + char_len > RICH_TEXT_CHUNK_SIZE:
            chunks.append("".join(current))
            current, current_len = [], 0
        current.append(char)
        current_len += char_len
    if current:
        chunks.append("".join(current))
    if len(chunks) > RICH_TEXT_MAX_ITEMS:
        raise InvalidPropertyValueError(
            f"Property '{prop_name}' text is too long (max {RICH_TEXT_CHUNK_SIZE * RICH_TEXT_MAX_ITEMS} characters)."
        )
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]


def _file_name(url: str) -> str:
    path = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return (path.rsplit("/", 1)[-1] or url)[:100]


def to_property_value(prop_name: str, prop_type: str, value: Any) -> dict:
    """Convert a simple value (string / number / bool / list) into the Notion API
    property value for prop_type. A dict already keyed by prop_type is passed through
    unchanged so callers can still send the raw Notion format when needed."""
    if prop_type in READ_ONLY_PROPERTY_TYPES:
        raise InvalidPropertyValueError(f"Property '{prop_name}' (type: {prop_type}) is read-only and cannot be set.")

    if isinstance(value, dict) and prop_type in value:
        if prop_type == "title" and not any(
            (item.get("text") or {}).get("content") or item.get("plain_text") or item.get("mention") or item.get("equation")
            for item in value["title"] or [] if isinstance(item, dict)
        ):
            raise InvalidPropertyValueError(f"Property '{prop_name}' is the title and cannot be empty.")
        return value

    empty = is_empty(value)

    if prop_type == "title":
        if empty:
            raise InvalidPropertyValueError(f"Property '{prop_name}' is the title and cannot be empty.")
        return {"title": to_rich_text(prop_name, value)}
    if prop_type == "rich_text":
        return {"rich_text": [] if empty else to_rich_text(prop_name, value)}
    if prop_type == "number":
        return {"number": None if empty else parse_number(prop_name, value)}
    if prop_type == "checkbox":
        return {"checkbox": parse_bool(prop_name, value)}
    if prop_type in ("select", "status"):
        return {prop_type: None if empty else {"name": _scalar_text(prop_name, prop_type, value)}}
    if prop_type == "multi_select":
        return {"multi_select": [{"name": name} for name in _parse_list(value)]}
    if prop_type == "date":
        return {"date": None if empty else parse_date(prop_name, value)}
    if prop_type in ("url", "email", "phone_number"):
        return {prop_type: None if empty else _scalar_text(prop_name, prop_type, value)}
    if prop_type in ("people", "relation"):
        return {prop_type: _parse_ids(prop_name, prop_type, value)}
    if prop_type == "files":
        return {
            "files": [
                {"name": _file_name(url), "type": "external", "external": {"url": url}}
                for url in _parse_list(value)
            ]
        }

    raise InvalidPropertyValueError(
        f"Property '{prop_name}' has unsupported type '{prop_type}'. "
        f"Pass the raw Notion format instead, e.g. {{\"{prop_type}\": ...}}."
    )


def build_properties_payload(values: dict, property_types: dict) -> dict:
    payload = {}
    for prop_name, value in values.items():
        if prop_name not in property_types:
            available = ", ".join(sorted(property_types))
            raise InvalidPropertyValueError(f"Property '{prop_name}' does not exist. Available properties: {available}")
        payload[prop_name] = to_property_value(prop_name, property_types[prop_name], value)
    return payload
