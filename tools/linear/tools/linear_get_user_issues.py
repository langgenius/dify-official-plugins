from typing import Dict, Any, Generator
import json
import re  # Import regex module

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear  # Use the client from the client directory
from client.Exceptions import LinearApiException, LinearAuthenticationException  # Import standard exceptions


class LinearGetUserIssuesTool(Tool):
    """Tool for retrieving issues assigned to a specific user in Linear."""

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:  # Renamed params to tool_parameters
        """Get issues assigned to a specific user."""
        # Check credentials
        if "linear_api_key" not in self.runtime.credentials or not self.runtime.credentials.get("linear_api_key"):
            yield self.create_text_message("Linear API Key is required.")
            return
            
        api_key = self.runtime.credentials.get("linear_api_key")
        
        try:
            # Initialize Linear client directly inside _invoke
            linear_client = Linear(api_key)
            
            # Extract parameters
            user_id = tool_parameters.get('userId', '').strip()
            team_id = tool_parameters.get('teamId', '').strip() if tool_parameters.get('teamId') else None
            state = tool_parameters.get('state', '').strip() if tool_parameters.get('state') else None
            limit = min(int(tool_parameters.get('limit', 10)), 50)  # Cap at 50 for performance
            
            # Define a simple regex pattern for UUID validation
            uuid_pattern = re.compile(
                r'^[a-f\d]{8}-([a-f\d]{4}-){3}[a-f\d]{12}$', re.IGNORECASE
            )

            # Validate required userId parameter and its format
            if not user_id:
                yield self.create_text_message("Error: userId is required")
                return
            
            if not uuid_pattern.match(user_id):
                yield self.create_text_message(f"Error: Invalid userId format. Please provide a valid UUID (e.g., '123e4567-e89b-12d3-a456-426614174000'). Provided: {user_id}")
                return

            # Build filter conditions
            filter_conditions = [f'assignee: {{ id: {{ eq: "{user_id}" }} }}']

            if team_id:
                filter_conditions.append(f'team: {{ id: {{ eq: "{team_id}" }} }}')

            if state:
                filter_conditions.append(f'state: {{ name: {{ eq: "{state}" }} }}')

            # Combine filter conditions
            filter_string = ", ".join(filter_conditions)

            # Build GraphQL query
            graphql_query = f"""
            query GetUserIssues {{
              issues(
                filter: {{ {filter_string} }},
                first: {limit}
              ) {{
                nodes {{
                  id
                  identifier
                  title
                  description
                  priority
                  url
                  state {{
                    id
                    name
                    type
                  }}
                  team {{
                    id
                    name
                  }}
                  labels {{
                    nodes {{
                      id
                      name
                      color
                    }}
                  }}
                  createdAt
                  updatedAt
                }}
              }}
            }}
            """

            # Use the new client's query method
            result = linear_client.query_graphql(graphql_query)
            
            # Response processing remains largely the same
            if result and 'data' in result and 'issues' in result.get('data', {}):
                issues_data = result['data']['issues']
                issues = issues_data.get('nodes', [])
                
                if not issues:
                    yield self.create_text_message(f"No issues found for user with ID {user_id}")
                    return
                
                # Format issues for better readability
                formatted_issues = []
                for issue in issues:
                    # Skip if essential data is missing
                    if not issue.get('identifier') or not issue.get('title'):
                        continue
                        
                    formatted_issue = {
                        "identifier": issue.get('identifier'),
                        "title": issue.get('title'),
                        "url": issue.get('url', f"https://linear.app/issue/{issue.get('identifier')}"),
                        "priority": issue.get('priority', 0),
                        "state": issue.get('state', {}).get('name') if issue.get('state') else None,
                        "team": issue.get('team', {}).get('name') if issue.get('team') else None,
                        "createdAt": issue.get('createdAt'),
                        "updatedAt": issue.get('updatedAt')
                    }
                    
                    # Safely handle labels
                    labels_data = []
                    if issue.get('labels') and issue.get('labels', {}).get('nodes'):
                        for label in issue.get('labels', {}).get('nodes', []):
                            if label.get('name'):
                                labels_data.append({
                                    "name": label.get('name'), 
                                    "color": label.get('color')
                                })
                    formatted_issue["labels"] = labels_data
                    
                    formatted_issues.append(formatted_issue)
                
                # If we have a session model, use it for summary
                if hasattr(self, 'session') and hasattr(self.session, 'model'):
                    try:
                        summary = self.session.model.summary(content=json.dumps(formatted_issues, ensure_ascii=False))
                        yield self.create_text_message(summary)
                    except Exception as e:
                        # Fallback to basic response on error
                        yield self.create_text_message(f"Found {len(formatted_issues)} issues for the user. Use a more specific query for detailed results.")
                else:
                    # Basic response if no model available
                    yield self.create_text_message(f"Found {len(formatted_issues)} issues for the user. Use a more specific query for detailed results.")
                
                return
                
            # Handle API errors (already handled by LinearApiException)
            # Removed explicit error handling for result['errors'] as query_graphql raises LinearApiException

            yield self.create_text_message("Error: Failed to retrieve user issues - unknown error")
            
        # Updated exception handling
        except LinearAuthenticationException:
            yield self.create_text_message("Authentication failed. Please check your Linear API key.")
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except ValueError as e: # Keep ValueError for things like int conversion
             yield self.create_text_message(f"Input error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}") 