from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools._endpoint import get_rpc_endpoint
from vanna.legacy.remote import VannaDefault


class VannaProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        endpoint = get_rpc_endpoint(credentials)
        client = VannaDefault(model="", api_key=credentials["api_key"], config={"endpoint": endpoint})
        try:
            models = client.get_models()
        except Exception as exc:
            raise ToolProviderCredentialValidationError(
                f"Could not connect to the Vanna RPC server: {exc}"
            ) from exc
        if not models:
            raise ToolProviderCredentialValidationError(
                "The Vanna RPC server did not return any models. Check the API key and model access."
            )
