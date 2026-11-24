from typing import Any

from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools._client import PocketRPCClient, PocketRPCError
from dify_plugin import ToolProvider


class PocketRPCProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validates the provider with a free live check.

        This plugin needs no credentials at all. Validation calls the free
        public Ethereum endpoint for the current block number and expects a
        real answer. It costs nothing and signs nothing.
        """
        try:
            client = PocketRPCClient()
            block_number = client.block_number("ethereum")
        except PocketRPCError as e:
            raise ToolProviderCredentialValidationError(str(e)) from None
        if not isinstance(block_number, int) or block_number <= 0:
            raise ToolProviderCredentialValidationError(
                "Validation check failed: the Pocket endpoint did not return "
                "a valid block number."
            )
