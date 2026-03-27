import json
from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearGetUsersTool(Tool):
    """Tool for searching users in Linear."""

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Search for users based on name or email."""
        # Check credentials
        if (
            "linear_api_key" not in self.runtime.credentials
            or not self.runtime.credentials.get("linear_api_key")
        ):
            yield self.create_text_message("Linear API Key is required.")
            return

        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            # Initialize Linear client
            linear_client = Linear(api_key)

            # Extract parameters
            name_query = tool_parameters.get("name", "").strip()
            email_query = tool_parameters.get("email", "").strip()
            limit = min(int(tool_parameters.get("limit", 10)), 50)  # Cap results

            if not name_query and not email_query:
                yield self.create_text_message(
                    "Error: Please provide either a name or email to search."
                )
                return

            # Use GraphQL variables to prevent injection attacks
            # Build filter object based on provided parameters
            filter_obj = {}

            if name_query and email_query:
                # AND condition if both name and email are provided
                filter_obj = {
                    "and": [
                        {
                            "or": [
                                {"name": {"containsIgnoreCase": name_query}},
                                {"displayName": {"containsIgnoreCase": name_query}},
                            ]
                        },
                        {"email": {"eq": email_query}},
                    ]
                }
            elif name_query:
                # Only name/displayName filter (OR condition)
                filter_obj = {
                    "or": [
                        {"name": {"containsIgnoreCase": name_query}},
                        {"displayName": {"containsIgnoreCase": name_query}},
                    ]
                }
            elif email_query:
                # Only email filter
                filter_obj = {"email": {"eq": email_query}}

            # Build GraphQL query
            graphql_query = """
            query GetUsers($filter: UserFilter!, $limit: Int!) {
              users(
                filter: $filter,
                first: $limit,
                orderBy: updatedAt
              ) {
                nodes {
                  id
                  name
                  email
                  displayName
                  active
                  createdAt
                  updatedAt
                }
              }
            }
            """

            variables = {"filter": filter_obj, "limit": limit}

            # Execute the query
            result = linear_client.query_graphql(graphql_query, variables)

            # Process the response
            if result and "data" in result and "users" in result.get("data", {}):
                users_data = result["data"]["users"]
                users = users_data.get("nodes", [])

                if not users:
                    search_criteria = f"{'name: ' + name_query if name_query else ''}{' email: ' + email_query if email_query else ''}".strip()
                    yield self.create_text_message(
                        f"No users found matching criteria: {search_criteria}"
                    )
                    return

                # Format users for better readability
                formatted_users = []
                for user in users:
                    formatted_user = {
                        "id": user.get("id"),
                        "name": user.get("name"),
                        "email": user.get("email"),
                        "displayName": user.get("displayName"),
                        "active": user.get("active"),
                    }
                    formatted_users.append(formatted_user)

                # Return results as JSON, wrapped in a dictionary
                yield self.create_json_message({"users": formatted_users})

            else:
                # This part might be redundant if query_graphql raises errors, but good fallback
                yield self.create_text_message(
                    "Error: Failed to retrieve users - unknown API response structure."
                )

        except LinearAuthenticationException:
            yield self.create_text_message(
                "Authentication failed. Please check your Linear API key."
            )
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except ValueError as e:  # Catch potential int conversion errors for limit
            yield self.create_text_message(f"Input error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
