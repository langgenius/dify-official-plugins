from typing import Dict, Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from .linear_client import LinearClient, LinearQueryException


class LinearAddCommentTool(Tool):
    """Tool for adding comments to issues in Linear."""

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
        """Add a comment to an issue in Linear.

        Args:
            params: Dictionary containing issueId and body parameters.

        Yields:
            A message with the result of the comment creation.
        """
        try:
            # Initialize the client
            self.client = self._get_linear_client()
            
            # Extract parameters
            issue_id = params.get('issueId')
            body = params.get('body', '')
            
            # Validate required parameters
            if not issue_id:
                yield self.create_text_message("Error: issueId is required")
                return
            
            if not body:
                yield self.create_text_message("Error: comment body is required")
                return
            
            # Sanitize inputs for GraphQL
            issue_id = str(issue_id).strip()
            body = body.replace('"', '\\"').replace('\n', '\\n')
            
            # Build GraphQL mutation
            graphql_mutation = f"""
            mutation AddComment {{
              commentCreate(
                input: {{
                  issueId: "{issue_id}",
                  body: "{body}"
                }}
              ) {{
                success
                comment {{
                  id
                  body
                  createdAt
                  user {{
                    id
                    name
                  }}
                }}
              }}
            }}
            """

            result = self.client.execute_graphql(graphql_mutation)
            
            if result and 'data' in result and 'commentCreate' in result.get('data', {}):
                comment_result = result['data']['commentCreate']
                
                if comment_result.get('success'):
                    comment = comment_result.get('comment', {})
                    
                    # Format the response
                    formatted_response = {
                        "success": True,
                        "message": "Comment added successfully",
                        "comment": {
                            "id": comment.get('id'),
                            "body": comment.get('body'),
                            "createdAt": comment.get('createdAt'),
                            "user": comment.get('user', {})
                        }
                    }
                    
                    yield self.create_text_message(f"Comment added successfully to issue {issue_id}")
                    return
                
            # Handle API errors
            if result and 'errors' in result:
                error_messages = [error.get('message', 'Unknown error') for error in result.get('errors', [])]
                error_message = '; '.join(error_messages)
                yield self.create_text_message(f"Error: {error_message}")
                return
            
            yield self.create_text_message("Error: Failed to add comment - unknown error")
            
        except ValueError as e:
            yield self.create_text_message(f"Error: {str(e)}")
        except LinearQueryException as e:
            yield self.create_text_message(f"Linear query error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}") 