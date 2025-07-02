from collections.abc import Generator
from typing import Any
import json
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class CreateImageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create an image from a template using APITemplate.io
        """
        try:
            # Get parameters
            template_id = tool_parameters.get("template_id", "").strip()
            overrides_data_str = tool_parameters.get("overrides_data", "").strip()
            output_image_type = tool_parameters.get("output_image_type", "all").strip()
            
            # Validate required parameters
            if not template_id:
                yield self.create_text_message("Template ID is required.")
                return
                
            if not overrides_data_str:
                yield self.create_text_message("Override data is required.")
                return
            
            # Parse override data
            try:
                overrides_data = json.loads(overrides_data_str)
            except json.JSONDecodeError as e:
                yield self.create_text_message(f"Invalid JSON override data: {str(e)}")
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
                "template_id": template_id
            }
            
            # Add output image type if specified
            if output_image_type and output_image_type != "all":
                params["output_image_type"] = output_image_type
            
            # Make API request
            response = requests.post(
                "https://rest.apitemplate.io/v2/create-image",
                headers=headers,
                json=overrides_data,
                params=params,
                timeout=60
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
                yield self.create_text_message(f"Image generation failed: {error_msg}")
                return
            
            # Extract information
            download_url = result.get("download_url", "")  # JPEG URL
            download_url_png = result.get("download_url_png", "")  # PNG URL
            transaction_ref = result.get("transaction_ref", "")
            
            # Create success response
            summary = "Image generated successfully!"
            if download_url and download_url_png:
                summary += " Both JPEG and PNG versions created."
            elif download_url:
                summary += " JPEG version created."
            elif download_url_png:
                summary += " PNG version created."
            
            yield self.create_text_message(summary)
            yield self.create_json_message({
                "status": "success",
                "download_url_jpeg": download_url,
                "download_url_png": download_url_png,
                "transaction_ref": transaction_ref,
                "template_id": template_id,
                "output_image_type": output_image_type
            })
            
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}") 