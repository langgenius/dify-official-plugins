from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dify_plugin.interfaces.agent import ToolEntity


def filter_allowed_tools(
    tools: list[ToolEntity] | None,
    allowed_tools: Any,
) -> list[ToolEntity] | None:
    """Return tools unchanged unless allowed_tools contains at least one name."""
    names = allowed_tool_names(allowed_tools)
    if names is None:
        return tools
    return [tool for tool in (tools or []) if tool.identity.name in names]


def allowed_tool_names(value: Any) -> set[str] | None:
    """Parse an optional allowlist. None/empty means no restriction."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            value = [stripped]
    if not isinstance(value, list) or not value:
        return None
    names = {
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    }
    return names or None


def coerce_allowed_tools(value: Any) -> list[str] | None:
    names = allowed_tool_names(value)
    return list(names) if names else None
