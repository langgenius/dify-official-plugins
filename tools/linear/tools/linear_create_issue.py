import json
from typing import Dict, Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear  # Use the client from the client directory
from client.Exceptions import LinearApiException, LinearAuthenticationException # Import standard exceptions


class LinearCreateIssueTool(Tool):
    """Tool for creating issues in Linear."""

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Create a new issue in Linear."""
        
        # Check credentials first
        if "linear_api_key" not in self.runtime.credentials or not self.runtime.credentials.get("linear_api_key"):
            yield self.create_text_message("Linear API Key is required.")
            return
            
        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            # Initialize the client inside _invoke
            linear_client = Linear(api_key)
            
            # Extract parameters
            title = tool_parameters.get('title', '').strip()
            team_id = tool_parameters.get('teamId', '').strip()
            description = tool_parameters.get('description', '').strip()
            assignee_id = tool_parameters.get('assigneeId', '').strip() if tool_parameters.get('assigneeId') else None
            priority_param = tool_parameters.get('priority') # Renamed to avoid conflict
            labels = tool_parameters.get('labels', []) # Assuming labels are passed as a list of IDs
            status_id = tool_parameters.get('statusId') # Get statusId if provided (might need adjustment in YAML too)

            # Validate required parameters
            if not title:
                yield self.create_text_message("Error: title is required")
                return
            
            if not team_id:
                yield self.create_text_message("Error: teamId is required")
                return
            
            # Build the input dictionary for the mutation variables
            mutation_input = {
                "title": title,
                "teamId": team_id, 
            }

            # Add optional fields if they exist
            if description:
                mutation_input["description"] = description
            if assignee_id:
                mutation_input["assigneeId"] = assignee_id
            if status_id: # Use statusId if available
                 mutation_input["stateId"] = status_id

            # Process priority safely
            if priority_param is not None:
                try:
                    priority_value = int(priority_param)
                    if 0 <= priority_value <= 4:
                        mutation_input["priority"] = priority_value
                    else:
                        yield self.create_text_message(f"Warning: Invalid priority value '{priority_param}'. Must be between 0 and 4. Skipping priority.")
                except (ValueError, TypeError):
                     yield self.create_text_message(f"Warning: Invalid priority format '{priority_param}'. Must be a number. Skipping priority.")

            # Process labels - ensure they are a list of strings (IDs)
            if labels:
                 if isinstance(labels, list) and all(isinstance(item, str) for item in labels):
                     mutation_input["labelIds"] = labels
                 else:
                      yield self.create_text_message(f"Warning: Invalid format for labels. Expected a list of strings (label IDs). Skipping labels.")

            # Define the GraphQL mutation using variables
            graphql_mutation = """
            mutation IssueCreate($input: IssueCreateInput!) {
              issueCreate(input: $input) {
                success
                issue {
                  id
                  title
                  description
                  priority
                  url
                  identifier
                  state { id name }
                  team { id name }
                  assignee { id name }
                  labels { nodes { id name } }
                }
              }
            }
            """
            
            # Execute using query_graphql with variables
            result = linear_client.query_graphql(
                query=graphql_mutation, 
                variables={"input": mutation_input}
            )
            
            # Process result (structure from query_graphql is slightly different)
            if result and 'data' in result and result['data'] and 'issueCreate' in result['data']:
                issue_result = result['data']['issueCreate']
                
                if issue_result and issue_result.get('success'):
                    issue = issue_result.get('issue', {})
                    if issue:
                         yield self.create_text_message(
                            f"Issue created successfully: {issue.get('identifier')} - {issue.get('title')}\nURL: {issue.get('url')}"
                         )
                         # Optionally yield full JSON data too
                         # yield self.create_json_message({"created_issue": issue})
                    else:
                        # Success was true but no issue data returned?
                        yield self.create_text_message("Issue created successfully, but no issue details were returned.")
                    return
                else:
                    # Handle success: false case if present
                    error_msg = "Failed to create issue. Reason unknown."
                    # Linear might provide more details within the issueCreate payload even on failure
                    yield self.create_text_message(f"Error: {error_msg}")
                    return
            
            # Fallback error if response structure is unexpected
            yield self.create_text_message("Error: Failed to create issue - unexpected API response.")

        # Updated exception handling
        except LinearAuthenticationException:
            yield self.create_text_message("Authentication failed. Please check your Linear API key.")
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except ValueError as e: # Catch potential int conversion errors
             yield self.create_text_message(f"Input error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}") 