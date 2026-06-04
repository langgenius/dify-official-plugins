from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider
from tools.get_cities import GetCitiesTool


class TempGuruProvider(ToolProvider):
    """
    TempGuru is a public read-only data API — no credentials are required.

    Validation strategy: invoke the lightest tool (get_cities, no parameters)
    once. If the HTTP roundtrip succeeds and returns the expected shape, the
    backend is reachable. Any exception is surfaced as a credential validation
    error so the user sees a useful message in the Dify UI.
    """

    def _validate_credentials(self, credentials: dict) -> None:
        try:
            for _ in GetCitiesTool.from_credentials(credentials).invoke_from_executor(
                tool_parameters={}
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Unable to reach TempGuru MCP REST API at mcp.tempguru.co: {str(e)}"
            )
