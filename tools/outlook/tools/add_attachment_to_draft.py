from collections.abc import Generator
from typing import Any
import requests
import urllib.parse
import base64
import mimetypes
import os

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class AddAttachmentToDraftTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Add attachments to an existing draft email using Microsoft Graph API
        """
        try:
            # Get parameters
            draft_id = tool_parameters.get("draft_id", "")
            files_to_attach = tool_parameters.get("file_to_attach")  # This is now a list of files
            attachment_name = tool_parameters.get("attachment_name", "")  
            # Get access token from OAuth credentials
            access_token = self.runtime.credentials.get("access_token")

            
            try:
                results = []
                for file_obj in files_to_attach:
                    # Read and encode file
                    file_data = self._read_and_encode_file(file_obj)
                    if isinstance(file_data, str):  # Error message
                        yield self.create_text_message(file_data)
                        continue
                    # Add attachment to draft
                    result = self._add_attachment_to_draft(
                        access_token, draft_id, file_data, 
                        attachment_name or file_data.get('name', 'attachment')
                    )
                    if isinstance(result, str):  # Error message
                        yield self.create_text_message(result)
                        continue
                    # Success
                    results.append(result)
                    yield self.create_text_message(f"Attachment '{result['name']}' added to draft successfully!")
                    yield self.create_json_message(result)
                if results:
                    yield self.create_text_message(f"Total {len(results)} attachment(s) added successfully.")
                else:
                    yield self.create_text_message("No attachments were added.")
                
            except Exception as e:
                yield self.create_text_message(f"Error adding attachment(s): {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
    
    def _read_and_encode_file(self, file_obj) -> dict:
        """
        Read file object from Dify and encode it for attachment
        """
        try:
            file_content = file_obj.blob  # Use 'blob' for file bytes
            file_name = file_obj.filename
            # Use file_obj.extension if available to ensure correct file extension
            file_extension = getattr(file_obj, 'extension', None)
            if file_extension and not file_name.endswith(file_extension):
                file_name += file_extension
            if isinstance(file_content, str):
                file_content = file_content.encode('utf-8')

            file_size = len(file_content)

            # Check file size limit (25MB for Graph API)
            if file_size > 25 * 1024 * 1024:
                return f"File too large: {file_size} bytes. Maximum size is 25MB."

            # Encode to base64
            encoded_content = base64.b64encode(file_content).decode('utf-8')

            # Get MIME type from filename
            mime_type, _ = mimetypes.guess_type(file_name)
            if not mime_type:
                mime_type = 'application/octet-stream'

            return {
                'content': encoded_content,
                'mime_type': mime_type,
                'size': file_size,
                'name': os.path.basename(file_name) if file_name else 'attachment'
            }
        except Exception as e:
            return f"Error processing file: {str(e)}"
    
    def _add_attachment_to_draft(self, access_token: str, draft_id: str, 
                                file_data: dict, attachment_name: str):
        """
        Add attachment to draft email using Microsoft Graph API
        """
        try:
            # URL encode the draft ID to handle special characters
            encoded_draft_id = urllib.parse.quote(draft_id, safe='')
            
            # Build attachment object
            attachment = {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": attachment_name,
                "contentType": file_data['mime_type'],
                "contentBytes": file_data['content'],
                "size": file_data['size']
            }
            
            # API endpoint using /me
            url = f"https://graph.microsoft.com/v1.0/me/messages/{encoded_draft_id}/attachments"
            
            # Headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # Make API request
            response = requests.post(url, headers=headers, json=attachment, timeout=60)
            
            # Handle response
            if response.status_code == 401:
                return "Authentication failed. Token may be expired."
            elif response.status_code == 403:
                return "Access denied. Check app permissions (Mail.ReadWrite required)."
            elif response.status_code == 404:
                return f"Draft with ID '{draft_id}' not found."
            elif response.status_code == 413:
                return "File too large. Maximum attachment size is 25MB."
            elif response.status_code not in [200, 201]:
                return f"API error {response.status_code}: {response.text}"
            
            # Parse response
            attachment_data = response.json()
            
            # Format response
            result = {
                "attachment_id": attachment_data.get("id"),
                "name": attachment_data.get("name"),
                "content_type": attachment_data.get("contentType"),
                "size": attachment_data.get("size"),
                "last_modified_datetime": attachment_data.get("lastModifiedDateTime"),
                "draft_id": draft_id,
                "is_inline": attachment_data.get("isInline", False)
            }
            
            return result
            
        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error adding attachment: {str(e)}"