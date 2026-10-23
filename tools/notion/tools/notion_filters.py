"""
Shared helpers for building Notion data source query filters and coercing
filter / property values. Used by query_database and update_database_record.
"""

from datetime import date
from typing import Any

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

# Maps a guess_scalar_type() result to its CONDITIONS_BY_GROUP key (used for formula / array rollup)
SCALAR_TYPE_TO_CONDITION_GROUP = {"number": "number", "checkbox": "checkbox", "date": "date", "string": "text"}


class InvalidFilterConditionError(ValueError):
    """Raised when filter_condition is not valid for the resolved property type."""


def validate_condition(group: str, filter_condition: str, filter_property: str, type_label: str) -> None:
    allowed = CONDITIONS_BY_GROUP[group]
    if filter_condition not in allowed:
        raise InvalidFilterConditionError(
            f"'{filter_condition}' is not a valid filter_condition for property '{filter_property}' "
            f"(type: {type_label}). Valid conditions: {', '.join(sorted(allowed))}"
        )


def condition_value(filter_condition: str, filter_value: str) -> Any:
    """Resolve the raw value to send for a condition, per Notion's fixed-value conditions."""
    if filter_condition in ("is_empty", "is_not_empty"):
        return True
    if filter_condition in ("past_week", "past_month", "past_year", "next_week", "next_month", "next_year", "this_week"):
        return {}
    return filter_value


def to_number(value: Any) -> Any:
    try:
        num_value = float(value)
        return int(num_value) if num_value == int(num_value) else num_value
    except (ValueError, TypeError, OverflowError):
        return value


def to_bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes")


def extract_person(person: dict) -> Any:
    if not person:
        return None
    return person.get("name") or person.get("id")


def guess_scalar_type(value: Any) -> str:
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


def build_filter(filter_property: str, filter_condition: str, filter_value: str,
                   property_type: str, prop_data: dict) -> dict:
    """Build a Notion API filter object for filter_property, validating filter_condition
    against the property's actual type. Raises InvalidFilterConditionError on a bad combination."""

    # Timestamp types use a different filter structure (no "property" key)
    if property_type in ("last_edited_time", "created_time"):
        validate_condition("date", filter_condition, filter_property, property_type)
        value = condition_value(filter_condition, filter_value)
        return {"timestamp": property_type, property_type: {filter_condition: value}}

    if property_type in CONDITION_GROUP_BY_PROPERTY_TYPE:
        group = CONDITION_GROUP_BY_PROPERTY_TYPE[property_type]
        validate_condition(group, filter_condition, filter_property, property_type)
        value = condition_value(filter_condition, filter_value)

        if property_type in ("number", "unique_id"):
            value = value if filter_condition in NO_VALUE_CONDITIONS else to_number(value)
        elif property_type == "checkbox":
            value = value if filter_condition in NO_VALUE_CONDITIONS else to_bool(value)
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
        sub_type = guess_scalar_type(filter_value)
        validate_condition(SCALAR_TYPE_TO_CONDITION_GROUP[sub_type], filter_condition, filter_property, f"formula ({sub_type})")
        value = condition_value(filter_condition, filter_value)
        if sub_type == "number":
            value = value if filter_condition in NO_VALUE_CONDITIONS else to_number(value)
        elif sub_type == "checkbox":
            value = value if filter_condition in NO_VALUE_CONDITIONS else to_bool(value)
        return {"property": filter_property, "formula": {sub_type: {filter_condition: value}}}

    if property_type == "rollup":
        rollup_function = (prop_data.get("rollup") or {}).get("function", "")
        if rollup_function in ROLLUP_NUMBER_FUNCTIONS:
            validate_condition("number", filter_condition, filter_property, "rollup (number)")
            value = condition_value(filter_condition, filter_value)
            value = value if filter_condition in NO_VALUE_CONDITIONS else to_number(value)
            return {"property": filter_property, "rollup": {"number": {filter_condition: value}}}
        if rollup_function in ROLLUP_DATE_FUNCTIONS:
            validate_condition("date", filter_condition, filter_property, "rollup (date)")
            value = condition_value(filter_condition, filter_value)
            return {"property": filter_property, "rollup": {"date": {filter_condition: value}}}
        # Array rollup (e.g. show_original): best-effort, defaults to "any" + inferred sub-type
        sub_type = guess_scalar_type(filter_value)
        validate_condition(SCALAR_TYPE_TO_CONDITION_GROUP[sub_type], filter_condition, filter_property, f"rollup array ({sub_type})")
        value = condition_value(filter_condition, filter_value)
        if sub_type == "number":
            value = value if filter_condition in NO_VALUE_CONDITIONS else to_number(value)
        elif sub_type == "checkbox":
            value = value if filter_condition in NO_VALUE_CONDITIONS else to_bool(value)
        # Notion's array-rollup filter uses the standard property filter key (rich_text), not "string"
        rollup_key = "rich_text" if sub_type == "string" else sub_type
        return {"property": filter_property, "rollup": {"any": {rollup_key: {filter_condition: value}}}}

    if property_type:
        # Unknown/unsupported property type: fall back to a rich_text-shaped filter
        value = condition_value(filter_condition, filter_value)
        return {"property": filter_property, "rich_text": {filter_condition: value}}

    # Property not found in the schema: fall back to a simple equals-style text filter
    return {"property": filter_property, "rich_text": {"equals": filter_value}}
