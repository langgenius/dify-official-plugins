from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.auth import auth


class ConfluenceProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """Validate Confluence credentials."""

        try:
            confluence = auth(credentials)
            confluence.get_all_spaces(limit=1)

        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Confluence authentication failed: {e}"
            )
