from collections.abc import Generator
from typing import Any
import json
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class CreatePdfFromHtmlTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a PDF from HTML using APITemplate.io
        """
        try:
            # Get parameters
            html_body = tool_parameters.get("html_body", "").strip()
            css_styles = tool_parameters.get("css_styles", "").strip()
            template_data_str = tool_parameters.get("template_data", "").strip()
            filename = tool_parameters.get("filename", "").strip()
            
            # Validate required parameters
            if not html_body:
                yield self.create_text_message("HTML body content is required.")
                return
            
            # Parse template data if provided
            template_data = {}
            if template_data_str:
                try:
                    template_data = json.loads(template_data_str)
                except json.JSONDecodeError as e:
                    yield self.create_text_message(f"Invalid JSON template data: {str(e)}")
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
                "export_type": "json"  # Return JSON with download URL
            }
            
            # Add filename if provided
            if filename:
                if not filename.endswith('.pdf'):
                    filename += '.pdf'
                params["filename"] = filename
            
            # Build request body
            request_body = {
                "body": html_body
            }
            
            if css_styles:
                request_body["css"] = css_styles
            
            if template_data:
                request_body["data"] = template_data
            
            # Make API request
            response = requests.post(
                "https://rest.apitemplate.io/v2/create-pdf-from-html",
                headers=headers,
                json=request_body,
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
            summary = f"PDF generated successfully from HTML! {total_pages} pages created."
            if filename:
                summary += f" Filename: {filename}"
            
            yield self.create_text_message(summary)
            yield self.create_json_message({
                "status": "success",
                "download_url": download_url,
                "total_pages": total_pages,
                "transaction_ref": transaction_ref,
                "filename": filename if filename else f"{transaction_ref}.pdf",
                "source": "html"
            })
            
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}") 