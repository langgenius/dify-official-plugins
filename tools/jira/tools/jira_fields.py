"""Parameter handling shared by several tools (kept out of the tool files: Dify loads one Tool class per file)."""

import json
from typing import Any

from tools.jira_client import JiraAuthError, JiraContext, jira_request, rich_text, segment


def split_list(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def user_ref(ctx: JiraContext, value: str) -> dict[str, str] | None:
    """An assignee reference: accountId on Cloud, username on Server; 'none' clears it."""
    if value.lower() in ("none", "unassigned", "-"):
        return None
    return {"accountId": value} if ctx.cloud else {"name": value}


def parse_custom_fields(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        fields = json.loads(str(value))
    except ValueError as e:
        raise JiraAuthError(
            f'custom_fields must be a JSON object, e.g. {{"customfield_10011": "Epic name"}}: {e}'
        ) from e
    if not isinstance(fields, dict):
        raise JiraAuthError("custom_fields must be a JSON object.")
    return fields


def issue_fields(ctx: JiraContext, tool_parameters: dict[str, Any]) -> dict[str, Any]:
    """The optional issue fields shared by create and update; only the parameters that were given."""
    fields: dict[str, Any] = {}
    if tool_parameters.get("summary"):
        fields["summary"] = str(tool_parameters["summary"])
    if tool_parameters.get("description"):
        fields["description"] = rich_text(ctx, str(tool_parameters["description"]))
    if tool_parameters.get("assignee"):
        fields["assignee"] = user_ref(ctx, str(tool_parameters["assignee"]).strip())
    if tool_parameters.get("priority"):
        fields["priority"] = {"name": str(tool_parameters["priority"]).strip()}
    labels = str(tool_parameters.get("labels") or "").strip()
    if labels:
        # Jira labels cannot contain spaces.
        fields["labels"] = [] if labels.lower() == "none" else [label.replace(" ", "_") for label in split_list(labels)]
    due = str(tool_parameters.get("due_date") or "").strip()
    if due:
        fields["duedate"] = None if due.lower() == "none" else due
    if tool_parameters.get("parent_key"):
        fields["parent"] = {"key": str(tool_parameters["parent_key"]).strip()}
    fields.update(parse_custom_fields(tool_parameters.get("custom_fields")))
    return fields


def list_transitions(ctx: JiraContext, key: str) -> list[dict[str, Any]]:
    body = jira_request(ctx, "GET", ctx.api(f"issue/{segment(key)}/transitions")).json()
    return [
        {"id": str(t.get("id", "")), "name": t.get("name", ""), "to_status": (t.get("to") or {}).get("name", "")}
        for t in body.get("transitions") or []
    ]


def match_transition(transitions: list[dict[str, Any]], wanted: str) -> dict[str, Any]:
    """A transition by ID, by name ('Start progress') or by target status ('In Progress')."""
    lowered = wanted.lower()
    for key in ("id", "name", "to_status"):
        for transition in transitions:
            if str(transition[key]).lower() == lowered:
                return transition
    options = ", ".join(f"{t['to_status']} ('{t['name']}', id {t['id']})" for t in transitions) or "none"
    raise JiraAuthError(f"No transition '{wanted}' is available on this issue now. Available: {options}.")
