from typing import Any
from dify_plugin import ToolProvider


class DingoProvider(ToolProvider):
    """
    Dingo tool provider for text quality evaluation and resume optimization.

    This provider does not require credentials as it provides stateless tools.
    """

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validate credentials (not required for Dingo tools).

        Dingo tools are stateless and do not require authentication.
        This method is implemented to comply with the ToolProvider interface.
        """
        # This plugin does not require credentials
        # Empty implementation to meet Dify plugin system interface requirements
        pass

