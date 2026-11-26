from urllib.parse import urlsplit

from dify_plugin.errors.tool import ToolProviderCredentialValidationError


def get_rpc_endpoint(credentials: dict) -> str:
    endpoint = (credentials.get("base_url") or "").strip().rstrip("/")
    parsed = urlsplit(endpoint)
    if not parsed.hostname or parsed.hostname == "ask.vanna.ai":
        raise ToolProviderCredentialValidationError(
            "Vanna's hosted service has shut down. Enter the URL of a compatible legacy Vanna RPC server."
        )
    if parsed.scheme not in {"http", "https"}:
        raise ToolProviderCredentialValidationError("The Vanna RPC URL must start with http:// or https://.")
    return endpoint
