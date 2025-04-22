import json
from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException

class LinearGetTeamsTool(Tool):
    """Tool for searching teams in Linear."""

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Search for teams based on name."""
        # Check credentials
        if "linear_api_key" not in self.runtime.credentials or not self.runtime.credentials.get("linear_api_key"):
            yield self.create_text_message("Linear API Key is required.")
            return
            
        api_key = self.runtime.credentials.get("linear_api_key")
        
        try:
            # Initialize Linear client
            linear_client = Linear(api_key)
            
            # Extract parameters
            name_query = tool_parameters.get('name', '').strip()
            limit = min(int(tool_parameters.get('limit', 10)), 50) # Cap results

            # Build filter string only if name_query is provided
            filter_string = ""
            if name_query:
                # Use containsIgnoreCase for broader name matching
                filter_string = f'filter: {{ name: {{ containsIgnoreCase: "{name_query}" }} }}'
            
            # Build GraphQL query
            # Note: Linear API uses `teams` query. Filtering might be applied.
            graphql_query = f"""
            query GetTeams {{
              teams(
                {filter_string} 
                first: {limit},
                orderBy: updatedAt
              ) {{
                nodes {{
                  id
                  name
                  key # Team Key is often useful
                  description
                  private
                  createdAt
                  updatedAt
                }}
              }}
            }}
            """

            # Execute the query
            result = linear_client.query_graphql(graphql_query)
            
            # Process the response
            if result and 'data' in result and 'teams' in result.get('data', {}):
                teams_data = result['data']['teams']
                teams = teams_data.get('nodes', [])
                
                if not teams:
                    search_criteria = f"name: {name_query}" if name_query else "(no filter)"
                    yield self.create_text_message(f"No teams found matching criteria: {search_criteria}")
                    return
                
                # Format teams for better readability
                formatted_teams = []
                for team in teams:
                    formatted_team = {
                        "id": team.get('id'),
                        "name": team.get('name'),
                        "key": team.get('key'),
                        "description": team.get('description'),
                        "private": team.get('private'),
                    }
                    formatted_teams.append(formatted_team)
                
                # Return results as JSON, wrapped in a dictionary
                yield self.create_json_message({"teams": formatted_teams})

            else:
                 yield self.create_text_message("Error: Failed to retrieve teams - unknown API response structure.")

        except LinearAuthenticationException:
            yield self.create_text_message("Authentication failed. Please check your Linear API key.")
        except LinearApiException as e:
            # Provide more specific error if filter is invalid
            if "Invalid filter" in str(e) or "Unknown argument" in str(e):
                 yield self.create_text_message(f"Linear API error: The provided filter might be invalid. Details: {str(e)}")
            else:
                 yield self.create_text_message(f"Linear API error: {str(e)}")
        except ValueError as e: # Catch potential int conversion errors for limit
             yield self.create_text_message(f"Input error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}") 