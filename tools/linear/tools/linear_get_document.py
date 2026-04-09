from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearGetDocumentTool(Tool):
    """Tool for retrieving a specific document from Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Get a Linear document by ID."""
        if (
            "linear_api_key" not in self.runtime.credentials
            or not self.runtime.credentials.get("linear_api_key")
        ):
            yield self.create_text_message("Linear API Key is required.")
            return

        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            document_id = tool_parameters.get("id", "").strip()
            if not document_id:
                yield self.create_text_message("Error: Document ID ('id') is required.")
                return

            linear_client = Linear(api_key)

            graphql_query = """
            query GetDocument($id: String!) {
              document(id: $id) {
                id
                title
                content
                url
                createdAt
                updatedAt
              }
            }
            """

            result = linear_client.query_graphql(
                graphql_query, variables={"id": document_id}
            )

            if result and "data" in result and "document" in result.get("data", {}):
                document = result["data"]["document"]
                if not document:
                    yield self.create_text_message(
                        f"No document found with ID: {document_id}"
                    )
                    return

                formatted_document = {
                    "id": document.get("id"),
                    "title": document.get("title"),
                    "content": document.get("content"),
                    "url": document.get("url"),
                    "createdAt": document.get("createdAt"),
                    "updatedAt": document.get("updatedAt"),
                }

                yield self.create_json_message(formatted_document)
            else:
                yield self.create_text_message(
                    "Error: Failed to retrieve document - unknown API response structure."
                )

        except LinearAuthenticationException:
            yield self.create_text_message(
                "Authentication failed. Please check your Linear API key."
            )
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
