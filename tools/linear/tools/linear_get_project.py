from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearGetProjectTool(Tool):
    """Tool for retrieving a specific project from Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Get a Linear project by ID."""
        if (
            "linear_api_key" not in self.runtime.credentials
            or not self.runtime.credentials.get("linear_api_key")
        ):
            yield self.create_text_message("Linear API Key is required.")
            return

        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            project_id = tool_parameters.get("id", "").strip()
            if not project_id:
                yield self.create_text_message("Error: Project ID ('id') is required.")
                return

            linear_client = Linear(api_key)

            graphql_query = """
            query GetProject($id: String!) {
              project(id: $id) {
                id
                name
                description
                state
                startDate
                targetDate
                createdAt
                updatedAt
                url
              }
            }
            """

            result = linear_client.query_graphql(
                graphql_query, variables={"id": project_id}
            )

            if result and "data" in result and "project" in result.get("data", {}):
                project = result["data"]["project"]
                if not project:
                    yield self.create_text_message(
                        f"No project found with ID: {project_id}"
                    )
                    return

                formatted_project = {
                    "id": project.get("id"),
                    "name": project.get("name"),
                    "description": project.get("description"),
                    "state": project.get("state"),
                    "startDate": project.get("startDate"),
                    "targetDate": project.get("targetDate"),
                    "createdAt": project.get("createdAt"),
                    "updatedAt": project.get("updatedAt"),
                    "url": project.get("url"),
                }

                yield self.create_json_message(formatted_project)
            else:
                yield self.create_text_message(
                    "Error: Failed to retrieve project - unknown API response structure."
                )

        except LinearAuthenticationException:
            yield self.create_text_message(
                "Authentication failed. Please check your Linear API key."
            )
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
