from typing import Any

from dify_plugin import ToolProvider


class ParallelProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """Parallel Search MCP does not require provider credentials."""
