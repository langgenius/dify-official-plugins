from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearListDocumentsTool(Tool):
    """Tool for listing documents in Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """List documents in Linear, optionally filtered by title."""
        if (
            "linear_api_key" not in self.runtime.credentials
            or not self.runtime.credentials.get("linear_api_key")
        ):
            yield self.create_text_message("Linear API Key is required.")
            return

        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            linear_client = Linear(api_key)

            query_text = tool_parameters.get("query", "").strip()
            limit = min(int(tool_parameters.get("limit", 10)), 50)

            filter_string = ""
            if query_text:
                filter_string = (
                    f'filter: {{ title: {{ containsIgnoreCase: "{query_text}" }} }}'
                )

            graphql_query = f"""
            query GetDocuments {{
              documents(
                {filter_string}
                first: {limit},
                orderBy: updatedAt
              ) {{
                nodes {{
                  id
                  title
                  createdAt
                  updatedAt
                }}
              }}
            }}
            """

            result = linear_client.query_graphql(graphql_query)

            if result and "data" in result and "documents" in result.get("data", {}):
                documents_data = result["data"]["documents"]
                documents = documents_data.get("nodes", [])

                if not documents:
                    search_criteria = (
                        f"query: {query_text}" if query_text else "(no filter)"
                    )
                    yield self.create_text_message(
                        f"No documents found matching criteria: {search_criteria}"
                    )
                    return

                formatted_documents = []
                for document in documents:
                    formatted_documents.append(
                        {
                            "id": document.get("id"),
                            "title": document.get("title"),
                            "createdAt": document.get("createdAt"),
                            "updatedAt": document.get("updatedAt"),
                        }
                    )

                yield self.create_json_message({"documents": formatted_documents})
            else:
                yield self.create_text_message(
                    "Error: Failed to retrieve documents - unknown API response structure."
                )

        except LinearAuthenticationException:
            yield self.create_text_message(
                "Authentication failed. Please check your Linear API key."
            )
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except ValueError as e:
            yield self.create_text_message(f"Input error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
