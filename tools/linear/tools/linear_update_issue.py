from typing import Dict, Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear  # Use the client from the client directory
from client.Exceptions import LinearApiException, LinearAuthenticationException, LinearResourceNotFoundException # Import standard exceptions


class LinearUpdateIssueTool(Tool):
    """Tool for updating issues in Linear."""

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Update an existing issue in Linear.

        Args:
            tool_parameters: Dictionary containing issueId and optional parameters like title,
                   description, state, assigneeId, priority, and labels.

        Yields:
            A message with the result of the issue update.
        """
        # Check credentials first
        if "linear_api_key" not in self.runtime.credentials or not self.runtime.credentials.get("linear_api_key"):
            yield self.create_text_message("Linear API Key is required.")
            return
        
        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            # Initialize the client inside _invoke
            linear_client = Linear(api_key)
            
            # Extract parameters - Use 'id' to match YAML
            issue_id = tool_parameters.get('id', '').strip()
            title = tool_parameters.get('title')
            description = tool_parameters.get('description')
            # Status is handled by stateId in the API
            state_id = tool_parameters.get('status') # Get status ID (from YAML 'status' param)
            assignee_id_param = tool_parameters.get('assigneeId') # Keep as None if not provided
            priority_param = tool_parameters.get('priority') # Keep as None if not provided
            labels = tool_parameters.get('labels') # Expecting list of IDs or None
            
            # Validate required issue ID
            if not issue_id:
                yield self.create_text_message("Error: Issue ID ('id') is required.")
                return
            
            # Build the update input dictionary dynamically
            update_input = {}
            updated_field_names = [] # For user feedback message

            if title is not None:
                update_input["title"] = str(title)
                updated_field_names.append("title")
            if description is not None:
                update_input["description"] = str(description)
                updated_field_names.append("description")
            if state_id:
                update_input["stateId"] = str(state_id)
                updated_field_names.append("status (stateId)")
            
            # Handle assignee update (including unassigning)
            if assignee_id_param is not None:
                if assignee_id_param == "" or assignee_id_param.lower() == "null" or assignee_id_param.lower() == "none":
                     update_input["assigneeId"] = None # Explicitly set to null for unassigning
                     updated_field_names.append("assignee (unassigned)")
                else:
                     update_input["assigneeId"] = str(assignee_id_param)
                     updated_field_names.append("assignee")

            # Handle priority update
            if priority_param is not None:
                try:
                    priority_value = int(priority_param)
                    if 0 <= priority_value <= 4:
                        update_input["priority"] = priority_value
                        updated_field_names.append(f"priority ({priority_value})")
                    else:
                        yield self.create_text_message(f"Warning: Invalid priority value '{priority_param}'. Must be 0-4. Skipping priority.")
                except (ValueError, TypeError):
                    yield self.create_text_message(f"Warning: Invalid priority format '{priority_param}'. Must be a number. Skipping priority.")

            # Handle labels update
            if labels is not None:
                 if isinstance(labels, list) and all(isinstance(item, str) for item in labels):
                     update_input["labelIds"] = labels
                     updated_field_names.append("labels")
                 elif isinstance(labels, str) and labels.strip(): # Handle comma-separated string?
                      try:
                           label_list = [l.strip() for l in labels.split(',') if l.strip()]
                           if label_list:
                                update_input["labelIds"] = label_list
                                updated_field_names.append("labels")
                           else: # Empty string after stripping/splitting
                                yield self.create_text_message(f"Warning: Provided labels string was empty after processing. Skipping labels update.")
                      except Exception:
                           yield self.create_text_message(f"Warning: Could not parse labels string '{labels}'. Skipping labels update.")
                 elif labels == []: # Explicitly empty list clears labels? Check API behavior
                      update_input["labelIds"] = [] # Assume empty list clears labels
                      updated_field_names.append("labels (cleared)")
                 else:
                      yield self.create_text_message(f"Warning: Invalid format for labels. Expected a list of strings (label IDs) or comma-separated string. Skipping labels update.")

            # Check if any fields were actually added for update
            if not update_input:
                yield self.create_text_message("Error: No valid fields provided to update.")
                return
            
            # Define the GraphQL mutation using variables
            graphql_mutation = """
            mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
              issueUpdate(id: $id, input: $input) {
                success
                issue {
                  id
                  identifier
                  title
                  url
                  # Add other fields shown in response as needed
                  state { id name }
                  priority
                }
              }
            }
            """

            # Execute using query_graphql with variables
            result = linear_client.query_graphql(
                query=graphql_mutation, 
                variables={"id": issue_id, "input": update_input}
            )

            # Process result
            if result and 'data' in result and result['data'] and 'issueUpdate' in result['data']:
                issue_result = result['data']['issueUpdate']
                
                if issue_result and issue_result.get('success'):
                    issue = issue_result.get('issue', {})
                    if issue:
                        fields_text = ", ".join(updated_field_names) if updated_field_names else "(no fields specified)"
                        yield self.create_text_message(
                            f"Issue {issue.get('identifier')} updated successfully.\n"
                            f"Updated fields: {fields_text}\n"
                            f"URL: {issue.get('url')}"
                        )
                    else:
                        yield self.create_text_message("Issue updated successfully, but no issue details were returned.")
                    return
                else:
                    error_msg = "Failed to update issue. Reason unknown."
                    yield self.create_text_message(f"Error: {error_msg}")
                    return
            
            # Fallback error if response structure is unexpected
            yield self.create_text_message("Error: Failed to update issue - unexpected API response.")

        # Updated exception handling
        except LinearAuthenticationException:
            yield self.create_text_message("Authentication failed. Please check your Linear API key.")
        except LinearResourceNotFoundException as e:
            yield self.create_text_message(f"Error: Issue with ID '{issue_id}' not found. Details: {str(e)}")
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except ValueError as e: # Catch potential int conversion errors
             yield self.create_text_message(f"Input error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}") 