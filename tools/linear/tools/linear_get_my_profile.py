import json
from typing import Any, Generator, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException

class LinearGetMyProfileTool(Tool):
    """Tool for retrieving the authenticated user's profile from Linear."""

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Gets the profile information of the user associated with the API key."""
        # Check credentials
        if "linear_api_key" not in self.runtime.credentials or not self.runtime.credentials.get("linear_api_key"):
            yield self.create_text_message("Linear API Key is required.")
            return
            
        api_key = self.runtime.credentials.get("linear_api_key")
        
        try:
            # Initialize Linear client
            linear_client = Linear(api_key)
            
            # Call the get_viewer method
            viewer_info = linear_client.get_viewer()
            
            if viewer_info:
                 # Return results as JSON
                 yield self.create_json_message(viewer_info)
            else:
                 # Should not happen if authentication works, but good practice
                 yield self.create_text_message("Error: Could not retrieve viewer information.")

        except LinearAuthenticationException:
            yield self.create_text_message("Authentication failed. Please check your Linear API key.")
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}") 