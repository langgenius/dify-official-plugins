from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearListProjectsTool(Tool):
    """Tool for listing projects in Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """List projects in Linear, optionally filtered by name."""
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

            # Use GraphQL variables to prevent injection attacks
            graphql_query = """
            query GetProjects($filter: ProjectFilter, $limit: Int!) {
              projects(
                filter: $filter,
                first: $limit,
                orderBy: updatedAt
              ) {
                nodes {
                  id
                  name
                  description
                  state
                  startDate
                  targetDate
                  createdAt
                  updatedAt
                }
              }
            }
            """

            variables = {"limit": limit}
            if name_query:
                variables["filter"] = {"name": {"containsIgnoreCase": name_query}}

            result = linear_client.query_graphql(graphql_query, variables)

            if result and "data" in result and "projects" in result.get("data", {}):
                projects_data = result["data"]["projects"]
                projects = projects_data.get("nodes", [])

                if not projects:
                    search_criteria = (
                        f"name: {name_query}" if name_query else "(no filter)"
                    )
                    yield self.create_text_message(
                        f"No projects found matching criteria: {search_criteria}"
                    )
                    return

                formatted_projects = []
                for project in projects:
                    formatted_projects.append(
                        {
                            "id": project.get("id"),
                            "name": project.get("name"),
                            "description": project.get("description"),
                            "state": project.get("state"),
                            "startDate": project.get("startDate"),
                            "targetDate": project.get("targetDate"),
                            "createdAt": project.get("createdAt"),
                            "updatedAt": project.get("updatedAt"),
                        }
                    )

                yield self.create_json_message({"projects": formatted_projects})
            else:
                yield self.create_text_message(
                    "Error: Failed to retrieve projects - unknown API response structure."
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
