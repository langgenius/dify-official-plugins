from collections.abc import Generator
from datetime import date, datetime
from typing import Any
import json
import math
import re

import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient
from tools.notion_filters import InvalidFilterConditionError, build_filter, to_bool

# Notion caps each rich_text / title text object at 2000 characters (counted in UTF-16 code units)
# and a rich_text array at 100 elements
RICH_TEXT_CHUNK_SIZE = 2000
RICH_TEXT_MAX_ITEMS = 100

# Default and hard upper bound for how many records one call may update
DEFAULT_MAX_UPDATES = 10
MAX_UPDATES_LIMIT = 1000

# How many matching records to echo back when refusing an ambiguous or oversized update
MAX_CANDIDATES_RETURNED = 10

# Property types computed or managed by Notion; the API rejects writes to them
READ_ONLY_PROPERTY_TYPES = {
    "formula", "rollup", "unique_id", "verification",
    "created_time", "created_by", "last_edited_time", "last_edited_by",
}

# Property types whose value can be matched exactly with an "equals" filter
MATCHABLE_PROPERTY_TYPES = {
    "title", "rich_text", "url", "email", "phone_number",
    "number", "unique_id", "select", "status", "checkbox", "date",
}

TRUE_STRINGS = {"true", "yes", "1"}
FALSE_STRINGS = {"false", "no", "0"}

# Notion stores numbers as IEEE 754 doubles, so integers beyond this cannot be represented exactly
MAX_SAFE_INTEGER = 2**53 - 1

INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")
UNIQUE_ID_PATTERN = re.compile(r"^(?:(\S+)-)?(\d+)$")


class InvalidPropertyValueError(ValueError):
    """Raised when a supplied value cannot be written to, or matched against, a property."""


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_bool(prop_name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = "" if value is None else str(value).strip().lower()
    if text in TRUE_STRINGS:
        return True
    if text in FALSE_STRINGS:
        return False
    raise InvalidPropertyValueError(f"Property '{prop_name}' (type: checkbox) requires true or false (got: {value!r}).")


def _parse_number(prop_name: str, value: Any) -> int | float:
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


def _parse_date(prop_name: str, value: Any) -> dict:
    if isinstance(value, dict):
        if not value.get("start"):
            raise InvalidPropertyValueError(f"Property '{prop_name}' (type: date) requires a 'start' value.")
        for key in ("start", "end"):
            if value.get(key):
                _parse_date(prop_name, value[key])
        return value
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
    if _is_empty(value):
        return []
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass
    if not isinstance(value, list):
        value = str(value).split(",")
    return [str(item).strip() for item in value if not _is_empty(item)]


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


def _to_rich_text(prop_name: str, value: Any) -> list:
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


def _to_property_value(prop_name: str, prop_type: str, value: Any) -> dict:
    """Convert a simple value (string / number / bool / list) into the Notion API
    property value for prop_type. A dict already keyed by prop_type is passed through
    unchanged so callers can still send the raw Notion format when needed."""
    if prop_type in READ_ONLY_PROPERTY_TYPES:
        raise InvalidPropertyValueError(f"Property '{prop_name}' (type: {prop_type}) is read-only and cannot be updated.")

    if isinstance(value, dict) and prop_type in value:
        if prop_type == "title" and not any(
            (item.get("text") or {}).get("content") or item.get("plain_text") or item.get("mention") or item.get("equation")
            for item in value["title"] or [] if isinstance(item, dict)
        ):
            raise InvalidPropertyValueError(f"Property '{prop_name}' is the title and cannot be cleared.")
        return value

    empty = _is_empty(value)

    if prop_type == "title":
        if empty:
            raise InvalidPropertyValueError(f"Property '{prop_name}' is the title and cannot be cleared.")
        return {"title": _to_rich_text(prop_name, value)}
    if prop_type == "rich_text":
        return {"rich_text": [] if empty else _to_rich_text(prop_name, value)}
    if prop_type == "number":
        return {"number": None if empty else _parse_number(prop_name, value)}
    if prop_type == "checkbox":
        return {"checkbox": _parse_bool(prop_name, value)}
    if prop_type in ("select", "status"):
        return {prop_type: None if empty else {"name": _scalar_text(prop_name, prop_type, value)}}
    if prop_type == "multi_select":
        return {"multi_select": [{"name": name} for name in _parse_list(value)]}
    if prop_type == "date":
        return {"date": None if empty else _parse_date(prop_name, value)}
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


def _build_properties_payload(values: dict, property_types: dict) -> dict:
    payload = {}
    for prop_name, value in values.items():
        if prop_name not in property_types:
            available = ", ".join(sorted(property_types))
            raise InvalidPropertyValueError(f"Property '{prop_name}' does not exist. Available properties: {available}")
        payload[prop_name] = _to_property_value(prop_name, property_types[prop_name], value)
    return payload


def _build_match_filter(match_property: str, match_value: str, prop_data: dict) -> dict:
    """Build an exact-match filter, normalising match_value for the property type first."""
    prop_type = prop_data.get("type")
    if prop_type not in MATCHABLE_PROPERTY_TYPES:
        raise InvalidPropertyValueError(
            f"Property '{match_property}' (type: {prop_type}) cannot be used as match_property. "
            f"Supported types: {', '.join(sorted(MATCHABLE_PROPERTY_TYPES))}."
        )
    if prop_type == "unique_id":
        # Accept the displayed form (e.g. "TASK-2") as well as the bare number
        found = UNIQUE_ID_PATTERN.match(match_value)
        if not found:
            raise InvalidPropertyValueError(
                f"Property '{match_property}' (type: unique_id) requires an ID number such as 2 or TASK-2 (got: {match_value!r})."
            )
        prefix = found.group(1)
        expected_prefix = (prop_data.get("unique_id") or {}).get("prefix") or ""
        if prefix is not None and prefix.lower() != expected_prefix.lower():
            expected = f"{expected_prefix}-<number>" if expected_prefix else "a number without a prefix"
            raise InvalidPropertyValueError(
                f"Property '{match_property}' (type: unique_id) expects {expected} (got: {match_value!r})."
            )
        number = int(found.group(2))
        if number > MAX_SAFE_INTEGER:
            raise InvalidPropertyValueError(f"Property '{match_property}' (type: unique_id) ID is too large (got: {match_value!r}).")
        # Built directly: build_filter's number coercion goes through float and would round large values
        return {"property": match_property, "unique_id": {"equals": number}}
    if prop_type == "number":
        return {"property": match_property, "number": {"equals": _parse_number(match_property, match_value)}}
    if prop_type == "checkbox":
        match_value = str(_parse_bool(match_property, match_value)).lower()
    elif prop_type == "date":
        _parse_date(match_property, match_value)
    return build_filter(match_property, "equals", match_value, prop_type, prop_data)


def _is_database_record(page_data: dict) -> bool:
    return page_data.get("parent", {}).get("type") in ("database_id", "data_source_id")


def _parent_database_id(page_data: dict) -> str:
    return (page_data.get("parent", {}).get("database_id") or "").replace("-", "").lower()


def _record(client: NotionClient, page_id: str) -> dict:
    return {"id": page_id, "url": client.format_page_url(page_id)}


class UpdateDatabaseRecordTool(Tool):
    def _result(self, status: str, message: str, **fields: Any) -> Generator[ToolInvokeMessage, None, None]:
        yield self.create_text_message(message)
        yield self.create_json_message({"status": status, "message": message, **fields})

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        page_id = str(tool_parameters.get("page_id") or "").strip()
        database_id = str(tool_parameters.get("database_id") or "").strip()
        match_property = str(tool_parameters.get("match_property") or "").strip()
        match_value = tool_parameters.get("match_value")
        match_value = "" if match_value is None else str(match_value).strip()
        properties_json = tool_parameters.get("properties") or ""
        update_all_matches = to_bool(tool_parameters.get("update_all_matches", False))
        try:
            max_updates = int(tool_parameters.get("max_updates") or DEFAULT_MAX_UPDATES)
        except (TypeError, ValueError):
            max_updates = DEFAULT_MAX_UPDATES
        max_updates = min(max(max_updates, 1), MAX_UPDATES_LIMIT)

        # Validate parameters
        if not page_id and not (database_id and match_property and match_value):
            yield from self._result(
                "invalid_input",
                "Either page_id, or database_id together with match_property and match_value, must be provided.",
            )
            return

        try:
            values = json.loads(properties_json) if isinstance(properties_json, str) else properties_json
        except json.JSONDecodeError:
            yield from self._result("invalid_input", "Invalid JSON format for properties. Please provide a valid JSON object.")
            return
        if not isinstance(values, dict) or not values:
            yield from self._result("invalid_input", "Properties must be a non-empty JSON object with property names as keys.")
            return

        # Get integration token from credentials
        integration_token = self.runtime.credentials.get("integration_token")
        if not integration_token:
            yield from self._result("error", "Notion Integration Token is required.")
            return

        # Initialize the Notion client
        client = NotionClient(integration_token)

        # Resolve the target records and convert the values for their property types
        try:
            if page_id:
                page_data = client.retrieve_page(page_id)
                if not _is_database_record(page_data):
                    yield from self._result("invalid_input", f"Page {page_id} is not a database record.")
                    return
                if database_id and _parent_database_id(page_data) != database_id.replace("-", "").lower():
                    yield from self._result(
                        "invalid_input", f"Page {page_id} does not belong to database {database_id}."
                    )
                    return
                property_types = {name: data.get("type") for name, data in page_data.get("properties", {}).items()}
                properties = _build_properties_payload(values, property_types)
                target_ids = [page_data.get("id") or page_id]
            else:
                data_source_id = client.get_default_data_source_id(database_id)
                schema = client.retrieve_data_source(data_source_id).get("properties", {})
                property_types = {name: data.get("type") for name, data in schema.items()}
                properties = _build_properties_payload(values, property_types)

                if match_property not in schema:
                    available = ", ".join(sorted(schema))
                    yield from self._result(
                        "invalid_input",
                        f"Match property '{match_property}' does not exist. Available properties: {available}",
                    )
                    return
                filter_obj = _build_match_filter(match_property, match_value, schema[match_property])

                # Collect one more match than allowed so an ambiguous or oversized update is refused before any write
                allowed = max_updates if update_all_matches else 1
                target_ids = []
                start_cursor = None
                while len(target_ids) <= allowed:
                    data = client.query_data_source(
                        data_source_id=data_source_id,
                        filter_obj=filter_obj,
                        page_size=min(100, allowed + 1 - len(target_ids)),
                        start_cursor=start_cursor,
                    )
                    target_ids.extend(result["id"] for result in data.get("results", []) if result.get("id"))
                    start_cursor = data.get("next_cursor")
                    if not data.get("has_more") or not start_cursor:
                        break

                condition = f"{match_property} = {match_value}"
                if not target_ids:
                    yield from self._result("not_found", f"No record found where {condition}.", matched_count=0)
                    return
                if len(target_ids) > allowed:
                    candidates = [_record(client, target_id) for target_id in target_ids[:MAX_CANDIDATES_RETURNED]]
                    if update_all_matches:
                        yield from self._result(
                            "too_many_matches",
                            f"More than {max_updates} records match {condition}. Nothing was updated. "
                            "Use a narrower match condition or raise max_updates.",
                            candidates=candidates,
                        )
                    else:
                        yield from self._result(
                            "ambiguous",
                            f"Multiple records match {condition}. Nothing was updated. "
                            "Pass page_id of the record to update, or use a unique match condition.",
                            candidates=candidates,
                        )
                    return
        except InvalidPropertyValueError as e:
            yield from self._result("invalid_input", str(e))
            return
        except InvalidFilterConditionError as e:
            yield from self._result("invalid_input", str(e))
            return
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                target = f"Page {page_id}" if page_id else f"Database {database_id}"
                yield from self._result(
                    "not_accessible",
                    f"{target} was not found or is not shared with this integration. "
                    "In Notion, open the database (or its parent page), choose ... > Connections, and add the integration.",
                )
            else:
                yield from self._result("error", f"Error looking up the record to update: {e}")
            return
        except Exception as e:
            yield from self._result("error", f"Error looking up the record to update: {e}")
            return

        # Update each target record; report progress even if one of them fails
        updated = []
        for index, target_id in enumerate(target_ids):
            try:
                client.update_page(target_id, properties)
            except Exception as e:
                yield from self._result(
                    "partially_updated" if updated else "error",
                    f"Error updating record {target_id}: {e}. Updated {len(updated)} of {len(target_ids)} records before the failure.",
                    matched_count=len(target_ids),
                    updated_count=len(updated),
                    updated_records=updated,
                    failed_record=_record(client, target_id),
                    pending_ids=target_ids[index + 1 :],
                    updated_properties=list(properties),
                )
                return
            updated.append(_record(client, target_id))

        yield from self._result(
            "updated",
            f"Successfully updated {len(updated)} record(s): {', '.join(properties)}",
            matched_count=len(target_ids),
            updated_count=len(updated),
            updated_records=updated,
            updated_properties=list(properties),
        )
