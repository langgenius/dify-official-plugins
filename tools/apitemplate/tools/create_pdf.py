from collections.abc import Generator
from typing import Any
import json
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class CreatePdfTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a PDF from a template using APITemplate.io
        """
        try:
            # Get parameters
            template_id = tool_parameters.get("template_id", "").strip()
            json_data_str = tool_parameters.get("json_data", "").strip()
            filename = tool_parameters.get("filename", "").strip()
            
            # Validate required parameters
            if not template_id:
                yield self.create_text_message("Template ID is required.")
                return
                
            if not json_data_str:
                yield self.create_text_message("JSON data is required.")
                return
            
            # Parse JSON data
            try:
                json_data = json.loads(json_data_str)
            except json.JSONDecodeError as e:
                yield self.create_text_message(f"Invalid JSON data: {str(e)}")
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
                "template_id": template_id,
                "export_type": "json"  # Return JSON with download URL
            }
            
            # Add filename if provided
            if filename:
                if not filename.endswith('.pdf'):
                    filename += '.pdf'
                params["filename"] = filename
            
            # Make API request
            response = requests.post(
                "https://rest.apitemplate.io/v2/create-pdf",
                headers=headers,
                json=json_data,
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
                yield self.create_text_message(f"PDF generation failed: {error_msg}")
                return
            
            # Extract information
            download_url = result.get("download_url", "")
            total_pages = result.get("total_pages", 0)
            transaction_ref = result.get("transaction_ref", "")
            
            # Create success response
            summary = f"PDF generated successfully! {total_pages} pages created."
            if filename:
                summary += f" Filename: {filename}"
            
            yield self.create_text_message(summary)
            yield self.create_json_message({
                "status": "success",
                "download_url": download_url,
                "total_pages": total_pages,
                "transaction_ref": transaction_ref,
                "template_id": template_id,
                "filename": filename if filename else f"{transaction_ref}.pdf"
            })
            
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}") 