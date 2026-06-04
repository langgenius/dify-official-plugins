import requests

from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider


class TempGuruProvider(ToolProvider):
    """
    TempGuru is a public read-only data API — no credentials are required.

    Validation strategy: probe the lightest REST endpoint (/cities, no
    parameters) once with a short timeout. If the HTTP roundtrip succeeds,
    the backend is reachable. Using a direct HTTP request avoids coupling
    this provider to the Tool subclass's internals and keeps the validator
    resilient to future Dify SDK changes.
    """

    def _validate_credentials(self, credentials: dict) -> None:
        try:
            response = requests.get(
                "https://mcp.tempguru.co/api/v1/cities",
                headers={
                    "User-Agent": "tempguru-dify-plugin/0.0.1",
                    "Accept": "application/json",
                },
                timeout=10,
            )
            response.raise_for_status()
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Unable to reach TempGuru MCP REST API at mcp.tempguru.co: {str(e)}"
            )
