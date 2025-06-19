from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class CreatePdfFromUrlTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a PDF from a URL using APITemplate.io
        """
        try:
            # Get parameters
            url = tool_parameters.get("url", "").strip()
            paper_size = tool_parameters.get("paper_size", "A4").strip()
            orientation = tool_parameters.get("orientation", "1").strip()
            filename = tool_parameters.get("filename", "").strip()
            
            # Validate required parameters
            if not url:
                yield self.create_text_message("URL is required.")
                return
            
            # Validate URL format
            if not url.startswith(("http://", "https://")):
                yield self.create_text_message("URL must start with http:// or https://")
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
                "url": url
            }
            
            # Add settings if provided
            settings = {}
            if paper_size and paper_size.upper() != "A4":
                settings["paper_size"] = paper_size.upper()
            if orientation and orientation != "1":
                settings["orientation"] = orientation
            
            if settings:
                request_body["settings"] = settings
            
            # Make API request
            response = requests.post(
                "https://rest.apitemplate.io/v2/create-pdf-from-url",
                headers=headers,
                json=request_body,
                params=params,
                timeout=120  # URL conversion might take longer
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
            summary = f"PDF generated successfully from URL! {total_pages} pages created."
            if filename:
                summary += f" Filename: {filename}"
            
            yield self.create_text_message(summary)
            yield self.create_json_message({
                "status": "success",
                "download_url": download_url,
                "total_pages": total_pages,
                "transaction_ref": transaction_ref,
                "source_url": url,
                "filename": filename if filename else f"{transaction_ref}.pdf",
                "source": "url"
            })
            
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}") 