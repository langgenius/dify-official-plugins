from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearGetUserTool(Tool):
    """Tool for retrieving a specific user from Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Get a Linear user by ID."""
        if (
            "linear_api_key" not in self.runtime.credentials
            or not self.runtime.credentials.get("linear_api_key")
        ):
            yield self.create_text_message("Linear API Key is required.")
            return

        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            user_id = tool_parameters.get("id", "").strip()
            if not user_id:
                yield self.create_text_message("Error: User ID ('id') is required.")
                return

            linear_client = Linear(api_key)

            graphql_query = """
            query GetUser($id: String!) {
              user(id: $id) {
                id
                name
                email
                displayName
                active
                createdAt
                updatedAt
              }
            }
            """

            result = linear_client.query_graphql(
                graphql_query, variables={"id": user_id}
            )

            if result and "data" in result and "user" in result.get("data", {}):
                user = result["data"]["user"]
                if not user:
                    yield self.create_text_message(f"No user found with ID: {user_id}")
                    return

                formatted_user = {
                    "id": user.get("id"),
                    "name": user.get("name"),
                    "email": user.get("email"),
                    "displayName": user.get("displayName"),
                    "active": user.get("active"),
                    "createdAt": user.get("createdAt"),
                    "updatedAt": user.get("updatedAt"),
                }

                yield self.create_json_message(formatted_user)
            else:
                yield self.create_text_message(
                    "Error: Failed to retrieve user - unknown API response structure."
                )

        except LinearAuthenticationException:
            yield self.create_text_message(
                "Authentication failed. Please check your Linear API key."
            )
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
