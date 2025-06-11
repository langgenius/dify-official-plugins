from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DeleteObjectTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Delete a PDF or image object using APITemplate.io
        """
        try:
            # Get parameters
            transaction_ref = tool_parameters.get("transaction_ref", "").strip()
            
            # Validate required parameters
            if not transaction_ref:
                yield self.create_text_message("Transaction reference is required.")
                return
            
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                yield self.create_text_message("APITemplate.io API key is not configured.")
                return
            
            # Prepare API request
            headers = {
                "X-API-KEY": api_key,
                "Content-Type": "application/json"
            }
            
            # Build query parameters
            params = {
                "transaction_ref": transaction_ref
            }
            
            # Make API request (DELETE operation using GET method)
            response = requests.get(
                "https://rest.apitemplate.io/v2/delete-object",
                headers=headers,
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = f"API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg = f"API Error: {error_data['message']}"
                except:
                    error_msg = f"API request failed with status {response.status_code}: {response.text}"
                
                yield self.create_text_message(error_msg)
                return
            
            # Parse response
            result = response.json()
            
            if result.get("status") != "success":
                error_msg = result.get("message", "Unknown error occurred")
                yield self.create_text_message(f"Delete operation failed: {error_msg}")
                return
            
            # Create success response
            summary = f"Object with transaction reference '{transaction_ref}' has been successfully deleted."
            
            yield self.create_text_message(summary)
            yield self.create_json_message({
                "status": "success",
                "transaction_ref": transaction_ref,
                "operation": "delete",
                "message": "Object deleted successfully"
            })
            
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}") 