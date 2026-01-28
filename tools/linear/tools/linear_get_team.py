from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearGetTeamTool(Tool):
    """Tool for retrieving a specific team from Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Get a Linear team by ID."""
        if (
            "linear_api_key" not in self.runtime.credentials
            or not self.runtime.credentials.get("linear_api_key")
        ):
            yield self.create_text_message("Linear API Key is required.")
            return

        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            team_id = tool_parameters.get("id", "").strip()
            if not team_id:
                yield self.create_text_message("Error: Team ID ('id') is required.")
                return

            linear_client = Linear(api_key)

            graphql_query = """
            query GetTeam($id: String!) {
              team(id: $id) {
                id
                name
                key
                description
                private
                createdAt
                updatedAt
              }
            }
            """

            result = linear_client.query_graphql(
                graphql_query, variables={"id": team_id}
            )

            if result and "data" in result and "team" in result.get("data", {}):
                team = result["data"]["team"]
                if not team:
                    yield self.create_text_message(f"No team found with ID: {team_id}")
                    return

                formatted_team = {
                    "id": team.get("id"),
                    "name": team.get("name"),
                    "key": team.get("key"),
                    "description": team.get("description"),
                    "private": team.get("private"),
                    "createdAt": team.get("createdAt"),
                    "updatedAt": team.get("updatedAt"),
                }

                yield self.create_json_message(formatted_team)
            else:
                yield self.create_text_message(
                    "Error: Failed to retrieve team - unknown API response structure."
                )

        except LinearAuthenticationException:
            yield self.create_text_message(
                "Authentication failed. Please check your Linear API key."
            )
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
