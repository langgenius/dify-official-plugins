from typing import Any
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.tavily_search import TavilySearchTool
from dify_plugin import ToolProvider


class TavilyProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validates the credentials by invoking the TavilySearchTool.
        A successful invocation that yields a JSON result first is considered valid.
        An invocation that yields a TEXT result first is considered a failure.
        """
        if not credentials.get("tavily_api_key"):
            raise ToolProviderCredentialValidationError("Tavily API key is missing.")

        try:
            tool = TavilySearchTool.from_credentials(credentials)
            result_generator = tool.invoke(
                tool_parameters={
                    "query": "dify ai",
                    "search_depth": "basic",
                    "max_results": 1,
                }
            )
            first_result = next(result_generator)

            if first_result.type == ToolInvokeMessage.MessageType.TEXT:
                # The tool yields a text message on failure.
                raise ToolProviderCredentialValidationError(str(first_result.message))

            # If the first message is not TEXT, we assume it's a success (e.g., JSON),
            # which indicates the API key is valid.

        except StopIteration:
            # The generator was empty, which is an unexpected state.
            raise ToolProviderCredentialValidationError(
                "Validation check failed: tool invocation produced no output."
            )
        except Exception as e:
            if isinstance(e, ToolProviderCredentialValidationError):
                raise e
            raise ToolProviderCredentialValidationError(
                f"An unexpected error occurred during validation: {str(e)}"
            )
