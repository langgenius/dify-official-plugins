from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from seltz import (
    Seltz,
    SeltzAPIError,
    SeltzAuthenticationError,
    SeltzConfigurationError,
    SeltzConnectionError,
    SeltzRateLimitError,
    SeltzTimeoutError,
)
from seltz.types import Includes


class SeltzSearchTool(Tool):
    """
    Tool for performing AI-powered searches using the Seltz API.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the Seltz search tool.

        Args:
            tool_parameters: Dictionary containing:
                - query: The search query text
                - max_documents: Maximum number of documents to return (default 10)

        Yields:
            ToolInvokeMessage: Search results as JSON messages
        """
        query = tool_parameters.get("query", "")
        if not query:
            yield self.create_text_message("Error: Search query is required.")
            return

        try:
            max_documents = int(tool_parameters.get("max_documents", 10))
        except (ValueError, TypeError):
            yield self.create_text_message(
                "Error: 'max_documents' must be a valid integer."
            )
            return

        # Get credentials
        api_key = self.runtime.credentials.get("api_key")
        if not api_key:
            yield self.create_text_message("Error: Seltz API key is not configured.")
            return

        try:
            # Initialize Seltz client
            client = Seltz(api_key=api_key)

            # Perform search
            response = client.search(query, includes=Includes(max_documents=max_documents))

            # Check if we have results
            if not response.documents:
                yield self.create_text_message(
                    f"No documents found for query: {query}"
                )
                return

            # Yield each document as a JSON message
            for document in response.documents:
                yield self.create_json_message(
                    {
                        "url": document.url,
                        "content": document.content,
                    }
                )

        except SeltzConfigurationError:
            yield self.create_text_message(
                "Configuration error: Please check your Seltz configuration."
            )
        except SeltzAuthenticationError:
            yield self.create_text_message(
                "Authentication error: Invalid API key. Please check your configuration."
            )
        except SeltzConnectionError:
            yield self.create_text_message(
                "Connection error: Unable to reach Seltz API. Please try again later."
            )
        except SeltzTimeoutError:
            yield self.create_text_message(
                "Timeout error: Request timed out. Please try again."
            )
        except SeltzRateLimitError:
            yield self.create_text_message(
                "Rate limit error: Too many requests. Please try again later."
            )
        except SeltzAPIError:
            yield self.create_text_message(
                "API error: An error occurred while communicating with Seltz."
            )
        except Exception:
            yield self.create_text_message(
                "An unexpected error occurred during the search."
            )
