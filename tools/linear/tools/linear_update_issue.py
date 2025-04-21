from typing import Dict, Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from .linear_client import LinearClient, LinearQueryException


class LinearUpdateIssueTool(Tool):
    """Tool for updating issues in Linear."""

    def __init__(self, **kwargs):
        """Initialize the tool with Linear client.
        
        Args:
            **kwargs: Additional arguments passed to the parent class.
        """
        super().__init__(**kwargs)
        self.client = None

    def _get_linear_client(self) -> LinearClient:
        """Get configured Linear client.
        
        Returns:
            Configured LinearClient instance
        """
        if not hasattr(self, 'runtime') or not self.runtime:
            raise ValueError("Runtime is not available")
        
        credentials = self.runtime.credentials or {}
        api_key = credentials.get('linear_api_key', '')
        
        if not api_key:
            raise ValueError("LINEAR_API_KEY is required.")
            
        return LinearClient(api_key=api_key)

    def _invoke(self, params: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Update an existing issue in Linear.

        Args:
            params: Dictionary containing issueId and optional parameters like title,
                   description, state, assigneeId, priority, and labels.

        Yields:
            A message with the result of the issue update.
        """
        try:
            # Initialize the client
            self.client = self._get_linear_client()
            
            # Extract parameters
            issue_id = params.get('issueId', '').strip()
            title = params.get('title')
            description = params.get('description')
            state_id = params.get('stateId', '').strip() if params.get('stateId') else None
            assignee_id = params.get('assigneeId', '').strip() if params.get('assigneeId') is not None else None
            priority = params.get('priority')
            labels = params.get('labels', [])
            
            # Validate required parameters
            if not issue_id:
                yield self.create_text_message("Error: issueId is required")
                return
            
            # Return error if no update fields are provided
            if not any([title is not None, description is not None, state_id, assignee_id is not None, priority is not None, labels]):
                yield self.create_text_message("Error: At least one field to update must be provided")
                return
            
            # Build GraphQL mutation input
            mutation_input = {
                "id": issue_id
            }

            if title is not None:
                mutation_input["title"] = str(title).replace('"', '\\"')

            if description is not None:
                mutation_input["description"] = str(description).replace('"', '\\"').replace('\n', '\\n')

            if state_id:
                mutation_input["stateId"] = state_id

            if assignee_id is not None:
                if assignee_id == "":
                    # To unassign an issue, we need to pass null
                    mutation_input["assigneeId"] = None
                else:
                    mutation_input["assigneeId"] = assignee_id

            if priority is not None:
                try:
                    priority_value = int(priority)
                    if priority_value >= 0 and priority_value <= 4:
                        mutation_input["priority"] = priority_value
                except (ValueError, TypeError):
                    pass
            
            # Format the input for GraphQL - handle special cases for strings and nulls
            mutation_input_str = ""
            for k, v in mutation_input.items():
                if k == "id":
                    mutation_input_str += f'{k}: "{v}", '
                elif v is None:
                    mutation_input_str += f'{k}: null, '
                elif isinstance(v, str):
                    mutation_input_str += f'{k}: "{v}", '
                else:
                    mutation_input_str += f'{k}: {v}, '
            
            # Handle labels
            labels_connection = ""
            if labels and isinstance(labels, list):
                label_ids = [f'"{label_id}"' for label_id in labels]
                labels_connection = f'labelIds: [{", ".join(label_ids)}]'
                if mutation_input_str:
                    mutation_input_str += labels_connection
                else:
                    mutation_input_str = labels_connection
            
            graphql_mutation = f"""
            mutation UpdateIssue {{
              issueUpdate(
                input: {{{mutation_input_str}}}
              ) {{
                success
                issue {{
                  id
                  title
                  description
                  priority
                  state {{
                    id
                    name
                  }}
                  assignee {{
                    id
                    name
                  }}
                  url
                  identifier
                }}
              }}
            }}
            """

            result = self.client.execute_graphql(graphql_mutation)
            
            if result and 'data' in result and 'issueUpdate' in result.get('data', {}):
                issue_result = result['data']['issueUpdate']
                
                if issue_result.get('success'):
                    issue = issue_result.get('issue', {})
                    
                    # Format response with safe gets
                    state_info = issue.get('state', {})
                    assignee_info = issue.get('assignee', {})
                    
                    # Create a user-friendly response
                    updated_fields = []
                    if title is not None:
                        updated_fields.append("title")
                    if description is not None:
                        updated_fields.append("description")
                    if state_id:
                        updated_fields.append("state")
                    if assignee_id is not None:
                        updated_fields.append("assignee")
                    if priority is not None:
                        updated_fields.append("priority")
                    if labels:
                        updated_fields.append("labels")
                    
                    fields_text = ", ".join(updated_fields)
                    
                    yield self.create_text_message(
                        f"Issue {issue.get('identifier')} updated successfully.\n"
                        f"Updated fields: {fields_text}\n"
                        f"URL: {issue.get('url')}"
                    )
                    return
                
            # Handle API errors
            if result and 'errors' in result:
                error_messages = [error.get('message', 'Unknown error') for error in result.get('errors', [])]
                error_message = '; '.join(error_messages)
                yield self.create_text_message(f"Error: {error_message}")
                return
            
            yield self.create_text_message("Error: Failed to update issue - unknown error")
            
        except ValueError as e:
            yield self.create_text_message(f"Error: {str(e)}")
        except LinearQueryException as e:
            yield self.create_text_message(f"Linear query error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}") 