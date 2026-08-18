from collections.abc import Generator
from datetime import date
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

# Conditions whose Notion API value is fixed (not taken from filter_value)
NO_VALUE_CONDITIONS = {
    "is_empty", "is_not_empty",
    "past_week", "past_month", "past_year",
    "next_week", "next_month", "next_year", "this_week",
}

# Rollup "function" values that produce a numeric result
ROLLUP_NUMBER_FUNCTIONS = {
    "count_all", "count_values", "count_unique_values", "count_empty",
    "count_not_empty", "percent_empty", "percent_not_empty",
    "sum", "average", "median", "min", "max", "range",
}

# Rollup "function" values that produce a date result
ROLLUP_DATE_FUNCTIONS = {"earliest_date", "latest_date", "date_range"}

# Valid filter_condition values per Notion property "shape" (see developers.notion.com/reference/post-database-query-filter)
CONDITIONS_BY_GROUP = {
    "text": {"equals", "does_not_equal", "contains", "does_not_contain", "starts_with", "ends_with", "is_empty", "is_not_empty"},
    "date": {"equals", "before", "after", "on_or_before", "on_or_after", "is_empty", "is_not_empty",
              "past_week", "past_month", "past_year", "next_week", "next_month", "next_year", "this_week"},
    "number": {"equals", "does_not_equal", "greater_than", "greater_than_or_equal_to", "less_than", "less_than_or_equal_to", "is_empty", "is_not_empty"},
    "checkbox": {"equals", "does_not_equal"},
    "select": {"equals", "does_not_equal", "is_empty", "is_not_empty"},
    "multi_select": {"contains", "does_not_contain", "is_empty", "is_not_empty"},
    "status": {"equals", "does_not_equal", "is_empty", "is_not_empty"},
    "people": {"contains", "does_not_contain", "is_empty", "is_not_empty"},
    "relation": {"contains", "does_not_contain", "is_empty", "is_not_empty"},
    "files": {"is_empty", "is_not_empty"},
    "unique_id": {"equals", "does_not_equal", "greater_than", "greater_than_or_equal_to", "less_than", "less_than_or_equal_to"},
}

# Maps a Notion property schema "type" to the CONDITIONS_BY_GROUP key that governs it
CONDITION_GROUP_BY_PROPERTY_TYPE = {
    "title": "text", "rich_text": "text", "url": "text", "email": "text", "phone_number": "text",
    "date": "date", "created_time": "date", "last_edited_time": "date",
    "number": "number",
    "checkbox": "checkbox",
    "select": "select",
    "multi_select": "multi_select",
    "status": "status",
    "people": "people", "created_by": "people", "last_edited_by": "people",
    "relation": "relation",
    "files": "files",
    "unique_id": "unique_id",
}

# Maps a _guess_scalar_type() result to its CONDITIONS_BY_GROUP key (used for formula / array rollup)
SCALAR_TYPE_TO_CONDITION_GROUP = {"number": "number", "checkbox": "checkbox", "date": "date", "string": "text"}


class InvalidFilterConditionError(ValueError):
    """Raised when filter_condition is not valid for the resolved property type."""


def _validate_condition(group: str, filter_condition: str, filter_property: str, type_label: str) -> None:
    allowed = CONDITIONS_BY_GROUP[group]
    if filter_condition not in allowed:
        raise InvalidFilterConditionError(
            f"'{filter_condition}' is not a valid filter_condition for property '{filter_property}' "
            f"(type: {type_label}). Valid conditions: {', '.join(sorted(allowed))}"
        )


def _condition_value(filter_condition: str, filter_value: str) -> Any:
    """Resolve the raw value to send for a condition, per Notion's fixed-value conditions."""
    if filter_condition in ("is_empty", "is_not_empty"):
        return True
    if filter_condition in ("past_week", "past_month", "past_year", "next_week", "next_month", "next_year", "this_week"):
        return {}
    return filter_value


def _to_number(value: Any) -> Any:
    try:
        num_value = float(value)
        return int(num_value) if num_value == int(num_value) else num_value
    except (ValueError, TypeError):
        return value


def _to_bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes")


def _extract_person(person: dict) -> Any:
    if not person:
        return None
    return person.get("name") or person.get("id")


def _guess_scalar_type(value: Any) -> str:
    """Best-effort inference of a formula/array-rollup result type from filter_value.
    Notion's schema API does not expose the computed result type, so this is a heuristic."""
    if value is None:
        return "string"
    text = str(value).strip()
    if text.lower() in ("true", "false"):
        return "checkbox"
    try:
        float(text)
        return "number"
    except (TypeError, ValueError):
        pass
    try:
        date.fromisoformat(text[:10])
        return "date"
    except ValueError:
        pass
    return "string"


def _build_filter(filter_property: str, filter_condition: str, filter_value: str,
                   property_type: str, prop_data: dict) -> dict:
    """Build a Notion API filter object for filter_property, validating filter_condition
    against the property's actual type. Raises InvalidFilterConditionError on a bad combination."""

    # Timestamp types use a different filter structure (no "property" key)
    if property_type in ("last_edited_time", "created_time"):
        _validate_condition("date", filter_condition, filter_property, property_type)
        value = _condition_value(filter_condition, filter_value)
        return {"timestamp": property_type, property_type: {filter_condition: value}}

    if property_type in CONDITION_GROUP_BY_PROPERTY_TYPE:
        group = CONDITION_GROUP_BY_PROPERTY_TYPE[property_type]
        _validate_condition(group, filter_condition, filter_property, property_type)
        value = _condition_value(filter_condition, filter_value)

        if property_type in ("number", "unique_id"):
            value = value if filter_condition in NO_VALUE_CONDITIONS else _to_number(value)
        elif property_type == "checkbox":
            value = value if filter_condition in NO_VALUE_CONDITIONS else _to_bool(value)
        elif property_type in ("people", "created_by", "last_edited_by"):
            # Notion's API uses the "people" filter key for all three property types
            return {"property": filter_property, "people": {filter_condition: value}}
        elif property_type == "files":
            # files only supports is_empty / is_not_empty (value is always true)
            return {"property": filter_property, "files": {filter_condition: True}}

        return {"property": filter_property, property_type: {filter_condition: value}}

    if property_type == "verification":
        # verification only supports the "status" condition (verified/expired/none)
        if filter_value not in ("verified", "expired", "none"):
            raise InvalidFilterConditionError(
                f"filter_value for verification property '{filter_property}' must be one of "
                f"'verified', 'expired', 'none' (got: '{filter_value}')"
            )
        return {"property": filter_property, "verification": {"status": filter_value}}

    if property_type == "formula":
        # Notion's schema API doesn't expose the formula's result type, so infer it from filter_value
        sub_type = _guess_scalar_type(filter_value)
        _validate_condition(SCALAR_TYPE_TO_CONDITION_GROUP[sub_type], filter_condition, filter_property, f"formula ({sub_type})")
        value = _condition_value(filter_condition, filter_value)
        if sub_type == "number":
            value = value if filter_condition in NO_VALUE_CONDITIONS else _to_number(value)
        elif sub_type == "checkbox":
            value = value if filter_condition in NO_VALUE_CONDITIONS else _to_bool(value)
        return {"property": filter_property, "formula": {sub_type: {filter_condition: value}}}

    if property_type == "rollup":
        rollup_function = (prop_data.get("rollup") or {}).get("function", "")
        if rollup_function in ROLLUP_NUMBER_FUNCTIONS:
            _validate_condition("number", filter_condition, filter_property, "rollup (number)")
            value = _condition_value(filter_condition, filter_value)
            value = value if filter_condition in NO_VALUE_CONDITIONS else _to_number(value)
            return {"property": filter_property, "rollup": {"number": {filter_condition: value}}}
        if rollup_function in ROLLUP_DATE_FUNCTIONS:
            _validate_condition("date", filter_condition, filter_property, "rollup (date)")
            value = _condition_value(filter_condition, filter_value)
            return {"property": filter_property, "rollup": {"date": {filter_condition: value}}}
        # Array rollup (e.g. show_original): best-effort, defaults to "any" + inferred sub-type
        sub_type = _guess_scalar_type(filter_value)
        _validate_condition(SCALAR_TYPE_TO_CONDITION_GROUP[sub_type], filter_condition, filter_property, f"rollup array ({sub_type})")
        value = _condition_value(filter_condition, filter_value)
        if sub_type == "number":
            value = value if filter_condition in NO_VALUE_CONDITIONS else _to_number(value)
        elif sub_type == "checkbox":
            value = value if filter_condition in NO_VALUE_CONDITIONS else _to_bool(value)
        # Notion's array-rollup filter uses the standard property filter key (rich_text), not "string"
        rollup_key = "rich_text" if sub_type == "string" else sub_type
        return {"property": filter_property, "rollup": {"any": {rollup_key: {filter_condition: value}}}}

    if property_type:
        # Unknown/unsupported property type: fall back to a rich_text-shaped filter
        value = _condition_value(filter_condition, filter_value)
        return {"property": filter_property, "rich_text": {filter_condition: value}}

    # Property not found in the schema: fall back to a simple equals-style text filter
    return {"property": filter_property, "rich_text": {"equals": filter_value}}


class QueryDatabaseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        database_id = tool_parameters.get("database_id", "")
        filter_property = tool_parameters.get("filter_property", "")
        filter_value = tool_parameters.get("filter_value", "")
        limit = int(tool_parameters.get("limit", 10))
        
        # Validate parameters
        if not database_id:
            yield self.create_text_message("Database ID is required.")
            return
            
        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return
                
            # Initialize the Notion client
            client = NotionClient(integration_token)
            
            # Prepare filter if a property is provided (value is optional for is_empty/is_not_empty/relative-date conditions)
            filter_condition = tool_parameters.get("filter_condition", "equals")
            filter_obj = None
            if filter_property and (filter_value or filter_condition in NO_VALUE_CONDITIONS):
                # Get database schema to determine the property type
                try:
                    data_source_id = client.get_default_data_source_id(database_id)
                    data_source = client.retrieve_data_source(data_source_id)
                    properties = data_source.get("properties", {})

                    # Find the property type (and its schema data, needed for rollup)
                    property_type = None
                    prop_data = {}
                    for prop_name, p_data in properties.items():
                        if prop_name == filter_property:
                            property_type = p_data.get("type")
                            prop_data = p_data
                            break

                    filter_obj = _build_filter(filter_property, filter_condition, filter_value, property_type, prop_data)
                except InvalidFilterConditionError as e:
                    yield self.create_text_message(str(e))
                    return
                except Exception:
                    filter_obj = client.create_simple_text_filter(filter_property, filter_value)
            
            # Query the database
            try:
                data = client.query_database(
                    database_id=database_id,
                    filter_obj=filter_obj,
                    page_size=limit
                )
                results = data.get("results", [])
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Database not found or you don't have access to it: {database_id}")
                else:
                    yield self.create_text_message(f"Error querying database: {e}")
                return
                
            if not results:
                filter_msg = f" with filter {filter_property}={filter_value}" if filter_property and filter_value else ""
                yield self.create_text_message(f"No results found in database{filter_msg}")
                return
                
            # Format results to extract and simplify property values
            formatted_results = []
            for result in results:
                # Get page ID and URL
                page_id = result.get("id")
                page_url = client.format_page_url(page_id)
                
                # Extract properties
                properties = result.get("properties", {})
                formatted_properties = {}
                
                for prop_name, prop_data in properties.items():
                    prop_type = prop_data.get("type")
                    
                    # Extract value based on property type
                    if prop_type == "title":
                        title_content = prop_data.get("title", [])
                        value = client.extract_plain_text(title_content)
                    elif prop_type == "rich_text":
                        text_content = prop_data.get("rich_text", [])
                        value = client.extract_plain_text(text_content)
                    elif prop_type == "number":
                        value = prop_data.get("number")
                    elif prop_type == "select":
                        select_data = prop_data.get("select", {})
                        value = select_data.get("name") if select_data else None
                    elif prop_type == "multi_select":
                        multi_select = prop_data.get("multi_select", [])
                        value = [item.get("name") for item in multi_select] if multi_select else []
                    elif prop_type == "date":
                        date_data = prop_data.get("date", {})
                        start = date_data.get("start") if date_data else None
                        end = date_data.get("end") if date_data else None
                        value = {"start": start, "end": end} if start else None
                    elif prop_type == "checkbox":
                        value = prop_data.get("checkbox")
                    elif prop_type == "url":
                        value = prop_data.get("url")
                    elif prop_type == "email":
                        value = prop_data.get("email")
                    elif prop_type == "phone_number":
                        value = prop_data.get("phone_number")
                    elif prop_type == "status":
                        status_data = prop_data.get("status", {})
                        value = status_data.get("name") if status_data else None
                    elif prop_type == "relation":
                        relation_data = prop_data.get("relation", [])
                        value = [item.get("id") for item in relation_data] if relation_data else []
                    elif prop_type in ("created_time", "last_edited_time"):
                        value = prop_data.get(prop_type)
                    elif prop_type in ("created_by", "last_edited_by"):
                        value = _extract_person(prop_data.get(prop_type, {}))
                    elif prop_type == "people":
                        people_data = prop_data.get("people", [])
                        value = [_extract_person(person) for person in people_data] if people_data else []
                    elif prop_type == "files":
                        files_data = prop_data.get("files", [])
                        value = []
                        for file_item in files_data:
                            file_url = (file_item.get("file") or file_item.get("external") or {}).get("url")
                            value.append({"name": file_item.get("name"), "url": file_url})
                    elif prop_type == "unique_id":
                        unique_id_data = prop_data.get("unique_id", {}) or {}
                        prefix = unique_id_data.get("prefix")
                        number = unique_id_data.get("number")
                        value = f"{prefix}-{number}" if prefix else number
                    elif prop_type == "verification":
                        verification_data = prop_data.get("verification") or {}
                        value = verification_data.get("state")
                    elif prop_type == "formula":
                        formula_data = prop_data.get("formula", {}) or {}
                        formula_result_type = formula_data.get("type")
                        value = formula_data.get(formula_result_type) if formula_result_type else None
                    elif prop_type == "rollup":
                        rollup_data = prop_data.get("rollup", {}) or {}
                        rollup_result_type = rollup_data.get("type")
                        value = rollup_data.get(rollup_result_type) if rollup_result_type else None
                    else:
                        # For other property types, just note the type
                        value = f"<{prop_type}>"
                    
                    formatted_properties[prop_name] = value
                
                # Add to formatted results
                formatted_results.append({
                    "id": page_id,
                    "url": page_url,
                    "properties": formatted_properties
                })
            
            # Return results
            filter_msg = f" with filter {filter_property}={filter_value}" if filter_property and filter_value else ""
            summary = f"Found {len(formatted_results)} results in database{filter_msg}"
            yield self.create_text_message(summary)
            yield self.create_json_message({"results": formatted_results})
            
        except Exception as e:
            yield self.create_text_message(f"Error querying Notion database: {str(e)}")
            return
