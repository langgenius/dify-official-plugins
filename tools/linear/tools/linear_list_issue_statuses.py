from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearListIssueStatusesTool(Tool):
    """Tool for listing issue statuses in Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """List issue statuses in Linear, optionally filtered by team."""
        if (
            "linear_api_key" not in self.runtime.credentials
            or not self.runtime.credentials.get("linear_api_key")
        ):
            yield self.create_text_message("Linear API Key is required.")
            return

        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            linear_client = Linear(api_key)

            team_id = tool_parameters.get("teamId", "").strip()
            limit = min(int(tool_parameters.get("limit", 10)), 50)

            # Use GraphQL variables to prevent injection attacks
            graphql_query = """
            query GetIssueStatuses($teamId: String, $limit: Int!) {
              workflowStates(
                filter: { team: { id: { eq: $teamId } } }
                first: $limit,
                orderBy: updatedAt
              ) {
                nodes {
                  id
                  name
                  type
                  position
                  team {
                    id
                    name
                  }
                }
              }
            }
            """

            variables = {"limit": limit}
            if team_id:
                variables["teamId"] = team_id

            result = linear_client.query_graphql(graphql_query, variables)

            if (
                result
                and "data" in result
                and "workflowStates" in result.get("data", {})
            ):
                statuses_data = result["data"]["workflowStates"]
                statuses = statuses_data.get("nodes", [])

                if not statuses:
                    search_criteria = f"teamId: {team_id}" if team_id else "(no filter)"
                    yield self.create_text_message(
                        f"No issue statuses found matching criteria: {search_criteria}"
                    )
                    return

                formatted_statuses = []
                for status in statuses:
                    formatted_statuses.append(
                        {
                            "id": status.get("id"),
                            "name": status.get("name"),
                            "type": status.get("type"),
                            "position": status.get("position"),
                            "team": {
                                "id": status.get("team", {}).get("id"),
                                "name": status.get("team", {}).get("name"),
                            }
                            if status.get("team")
                            else None,
                        }
                    )

                yield self.create_json_message({"issueStatuses": formatted_statuses})
            else:
                yield self.create_text_message(
                    "Error: Failed to retrieve issue statuses - unknown API response structure."
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
