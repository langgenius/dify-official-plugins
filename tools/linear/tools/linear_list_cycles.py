from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearListCyclesTool(Tool):
    """Tool for listing cycles in Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """List cycles in Linear, optionally filtered by team."""
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

            filter_string = ""
            if team_id:
                filter_string = f'filter: {{ team: {{ id: {{ eq: "{team_id}" }} }} }}'

            graphql_query = f"""
            query GetCycles {{
              cycles(
                {filter_string}
                first: {limit},
                orderBy: updatedAt
              ) {{
                nodes {{
                  id
                  number
                  name
                  startsAt
                  endsAt
                  team {{
                    id
                    name
                  }}
                }}
              }}
            }}
            """

            result = linear_client.query_graphql(graphql_query)

            if result and "data" in result and "cycles" in result.get("data", {}):
                cycles_data = result["data"]["cycles"]
                cycles = cycles_data.get("nodes", [])

                if not cycles:
                    search_criteria = f"teamId: {team_id}" if team_id else "(no filter)"
                    yield self.create_text_message(
                        f"No cycles found matching criteria: {search_criteria}"
                    )
                    return

                formatted_cycles = []
                for cycle in cycles:
                    formatted_cycles.append(
                        {
                            "id": cycle.get("id"),
                            "number": cycle.get("number"),
                            "name": cycle.get("name"),
                            "startsAt": cycle.get("startsAt"),
                            "endsAt": cycle.get("endsAt"),
                            "team": {
                                "id": cycle.get("team", {}).get("id"),
                                "name": cycle.get("team", {}).get("name"),
                            }
                            if cycle.get("team")
                            else None,
                        }
                    )

                yield self.create_json_message({"cycles": formatted_cycles})
            else:
                yield self.create_text_message(
                    "Error: Failed to retrieve cycles - unknown API response structure."
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
