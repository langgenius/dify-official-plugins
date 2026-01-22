from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearListIssueLabelsTool(Tool):
    """Tool for listing issue labels in Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """List issue labels in Linear, optionally filtered by name."""
        if (
            "linear_api_key" not in self.runtime.credentials
            or not self.runtime.credentials.get("linear_api_key")
        ):
            yield self.create_text_message("Linear API Key is required.")
            return

        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            linear_client = Linear(api_key)

            name_query = tool_parameters.get("name", "").strip()
            limit = min(int(tool_parameters.get("limit", 10)), 50)

            filter_string = ""
            if name_query:
                filter_string = (
                    f'filter: {{ name: {{ containsIgnoreCase: "{name_query}" }} }}'
                )

            graphql_query = f"""
            query GetIssueLabels {{
              issueLabels(
                {filter_string}
                first: {limit},
                orderBy: updatedAt
              ) {{
                nodes {{
                  id
                  name
                  color
                }}
              }}
            }}
            """

            result = linear_client.query_graphql(graphql_query)

            if result and "data" in result and "issueLabels" in result.get("data", {}):
                labels_data = result["data"]["issueLabels"]
                labels = labels_data.get("nodes", [])

                if not labels:
                    search_criteria = (
                        f"name: {name_query}" if name_query else "(no filter)"
                    )
                    yield self.create_text_message(
                        f"No issue labels found matching criteria: {search_criteria}"
                    )
                    return

                formatted_labels = []
                for label in labels:
                    formatted_labels.append(
                        {
                            "id": label.get("id"),
                            "name": label.get("name"),
                            "color": label.get("color"),
                        }
                    )

                yield self.create_json_message({"issueLabels": formatted_labels})
            else:
                yield self.create_text_message(
                    "Error: Failed to retrieve issue labels - unknown API response structure."
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
