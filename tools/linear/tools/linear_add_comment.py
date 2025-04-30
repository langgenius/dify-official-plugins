import json
from typing import Dict, Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear  # Use the client from the client directory
from client.Exceptions import LinearApiException, LinearAuthenticationException, LinearResourceNotFoundException # Import standard exceptions


class LinearAddCommentTool(Tool):
    """Tool for adding comments to issues in Linear."""

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Add a comment to an issue in Linear."""
        
        # Check credentials first
        if "linear_api_key" not in self.runtime.credentials or not self.runtime.credentials.get("linear_api_key"):
            yield self.create_text_message("Linear API Key is required.")
            return
            
        api_key = self.runtime.credentials.get("linear_api_key")

        try:
            # Initialize the client inside _invoke
            linear_client = Linear(api_key)
            
            # Extract parameters
            issue_id = tool_parameters.get('issueId', '').strip()
            body = tool_parameters.get('body', '').strip() # Don't strip by default? Let user control formatting?
            create_as_user = tool_parameters.get('createAsUser')
            display_icon_url = tool_parameters.get('displayIconUrl')

            # Validate required parameters
            if not issue_id:
                yield self.create_text_message("Error: issueId is required")
                return
            
            if not body:
                yield self.create_text_message("Error: comment body is required")
                return

            # Build the input dictionary for the mutation variables
            mutation_input = {
                "issueId": issue_id,
                "body": body, 
            }

            # Add optional fields if they exist and are not empty strings
            if create_as_user and str(create_as_user).strip():
                mutation_input["createAsUser"] = str(create_as_user).strip()
            if display_icon_url and str(display_icon_url).strip():
                mutation_input["displayIconUrl"] = str(display_icon_url).strip()

            # Define the GraphQL mutation using variables
            graphql_mutation = """
            mutation CommentCreate($input: CommentCreateInput!) {
              commentCreate(input: $input) {
                success
                comment {
                  id
                  body
                  createdAt
                  user { id name }
                  # Add other fields if needed, like editedAt, resolvedAt
                }
              }
            }
            """
            
            # Execute using query_graphql with variables
            result = linear_client.query_graphql(
                query=graphql_mutation, 
                variables={"input": mutation_input}
            )
            
            # Process result
            if result and 'data' in result and result['data'] and 'commentCreate' in result['data']:
                comment_result = result['data']['commentCreate']
                
                if comment_result and comment_result.get('success'):
                    comment = comment_result.get('comment', {})
                    if comment:
                         yield self.create_text_message(f"Comment added successfully to issue {issue_id}. Comment ID: {comment.get('id')}")
                         # Optionally yield full JSON data too
                         # yield self.create_json_message({"created_comment": comment})
                    else:
                         # Success was true but no comment data returned?
                         yield self.create_text_message("Comment added successfully, but no comment details were returned.")
                    return
                else:
                    # Handle success: false case if present
                    error_msg = "Failed to add comment. Reason unknown."
                    yield self.create_text_message(f"Error: {error_msg}")
                    return
            
            # Fallback error if response structure is unexpected
            yield self.create_text_message("Error: Failed to add comment - unexpected API response.")

        # Updated exception handling
        except LinearAuthenticationException:
            yield self.create_text_message("Authentication failed. Please check your Linear API key.")
        except LinearResourceNotFoundException as e:
            # Linear might return a generic API error or validation error if issueId is wrong
            yield self.create_text_message(f"Error adding comment: Issue with ID '{issue_id}' might not exist or cannot be commented on. Details: {str(e)}")
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except ValueError as e: # Catch potential type errors if needed
             yield self.create_text_message(f"Input error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}") 