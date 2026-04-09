from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearGetIssueTool(Tool):
    """Tool for retrieving a specific issue from Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Get a Linear issue by ID."""
        if (
            "linear_api_key" not in self.runtime.credentials
            or not self.runtime.credentials.get("linear_api_key")
        ):
            yield self.create_text_message("Linear API Key is required.")
            return

        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            issue_id = tool_parameters.get("id", "").strip()
            if not issue_id:
                yield self.create_text_message("Error: Issue ID ('id') is required.")
                return

            linear_client = Linear(api_key)

            graphql_query = """
            query GetIssue($id: String!) {
              issue(id: $id) {
                id
                identifier
                title
                description
                priority
                url
                createdAt
                updatedAt
                state {
                  id
                  name
                  type
                }
                assignee {
                  id
                  name
                }
                labels {
                  nodes {
                    id
                    name
                    color
                  }
                }
              }
            }
            """

            result = linear_client.query_graphql(
                graphql_query, variables={"id": issue_id}
            )

            if result and "data" in result and "issue" in result.get("data", {}):
                issue = result["data"]["issue"]
                if not issue:
                    yield self.create_text_message(
                        f"No issue found with ID: {issue_id}"
                    )
                    return

                formatted_issue = {
                    "id": issue.get("id"),
                    "identifier": issue.get("identifier"),
                    "title": issue.get("title"),
                    "description": issue.get("description"),
                    "priority": issue.get("priority"),
                    "url": issue.get("url"),
                    "createdAt": issue.get("createdAt"),
                    "updatedAt": issue.get("updatedAt"),
                    "state": issue.get("state"),
                    "assignee": issue.get("assignee"),
                    "labels": issue.get("labels", {}).get("nodes", [])
                    if issue.get("labels")
                    else [],
                }

                yield self.create_json_message(formatted_issue)
            else:
                yield self.create_text_message(
                    "Error: Failed to retrieve issue - unknown API response structure."
                )

        except LinearAuthenticationException:
            yield self.create_text_message(
                "Authentication failed. Please check your Linear API key."
            )
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
