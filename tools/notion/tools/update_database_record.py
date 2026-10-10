from collections.abc import Generator
from typing import Any
import json
import re

import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient, extract_notion_id
from tools.notion_filters import InvalidFilterConditionError, build_filter, to_bool
from tools.notion_properties import (
    MAX_SAFE_INTEGER,
    InvalidPropertyValueError,
    build_properties_payload,
    parse_bool,
    parse_date,
    parse_number,
)

# Default and hard upper bound for how many records one call may update
DEFAULT_MAX_UPDATES = 10
MAX_UPDATES_LIMIT = 1000

# How many matching records to echo back when refusing an ambiguous or oversized update
MAX_CANDIDATES_RETURNED = 10

# Property types whose value can be matched exactly with an "equals" filter
MATCHABLE_PROPERTY_TYPES = {
    "title", "rich_text", "url", "email", "phone_number",
    "number", "unique_id", "select", "status", "checkbox", "date",
}

UNIQUE_ID_PATTERN = re.compile(r"^(?:(\S+)-)?(\d+)$")


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
        return {"property": match_property, "number": {"equals": parse_number(match_property, match_value)}}
    if prop_type == "checkbox":
        match_value = str(parse_bool(match_property, match_value)).lower()
    elif prop_type == "date":
        parse_date(match_property, match_value)
    return build_filter(match_property, "equals", match_value, prop_type, prop_data)


def _is_database_record(page_data: dict) -> bool:
    return page_data.get("parent", {}).get("type") in ("database_id", "data_source_id")


def _normalize_id(value: str) -> str:
    return extract_notion_id(value).replace("-", "").lower()


def _parent_ids(page_data: dict) -> set[str]:
    """IDs of the database and data source a record belongs to, normalised for comparison."""
    parent = page_data.get("parent", {})
    return {_normalize_id(parent[key]) for key in ("database_id", "data_source_id") if parent.get(key)}


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
                if database_id and _normalize_id(database_id) not in _parent_ids(page_data):
                    yield from self._result(
                        "invalid_input", f"Page {page_id} does not belong to database {database_id}."
                    )
                    return
                property_types = {name: data.get("type") for name, data in page_data.get("properties", {}).items()}
                properties = build_properties_payload(values, property_types)
                target_ids = [page_data.get("id") or page_id]
            else:
                data_source = client.resolve_data_source(database_id)
                data_source_id = data_source.get("id", "")
                schema = data_source.get("properties", {})
                property_types = {name: data.get("type") for name, data in schema.items()}
                properties = build_properties_payload(values, property_types)

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
