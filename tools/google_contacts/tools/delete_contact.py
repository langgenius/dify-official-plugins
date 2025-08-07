from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class DeleteContactTool(Tool):
    """
    Tool to delete a contact from Google Contacts.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Delete a contact from Google Contacts API.

        Args:
            tool_parameters: Dictionary containing tool parameters
        """
        try:
            # Extract required parameters
            resource_name = tool_parameters.get("resource_name", "").strip()
            if not resource_name:
                yield self.create_text_message(
                    "Resource name is required (e.g., 'people/123456789')"
                )
                return

            # Get confirmation parameter
            confirm_delete = tool_parameters.get("confirm_delete", False)
            if not confirm_delete:
                yield self.create_text_message(
                    "To delete a contact, you must set confirm_delete to true. This action cannot be undone."
                )
                return

            # Get access token
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message(
                    "Access token not found. Please authenticate first."
                )
                return

            # First, get contact info to show what will be deleted
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            # Get contact info before deletion
            get_response = requests.get(
                f"https://people.googleapis.com/v1/{resource_name}?personFields=names,phoneNumbers,emailAddresses",
                headers=headers,
                timeout=30,
            )

            contact_name = "Unknown Contact"
            if get_response.status_code == 200:
                contact_data = get_response.json()
                names = contact_data.get("names", [])
                if names:
                    contact_name = names[0].get("displayName", "Unknown Contact")

            # Log the operation
            yield self.create_log_message(
                label="Deleting Contact",
                data={"resource_name": resource_name, "contact_name": contact_name},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
            )

            # Make API request to delete contact
            delete_response = requests.delete(
                f"https://people.googleapis.com/v1/{resource_name}:deleteContact",
                headers=headers,
                timeout=30,
            )

            if delete_response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate your Google account."
                )
                return
            elif delete_response.status_code == 403:
                yield self.create_text_message(
                    "Permission denied. Please ensure you have granted contacts write access."
                )
                return
            elif delete_response.status_code == 404:
                yield self.create_text_message(
                    f"Contact not found. The resource name '{resource_name}' may be invalid or the contact may already be deleted."
                )
                return
            elif delete_response.status_code != 200:
                yield self.create_text_message(
                    f"API request failed with status {delete_response.status_code}: {delete_response.text}"
                )
                return

            # Create result
            result_data = {
                "success": True,
                "message": f"Contact '{contact_name}' deleted successfully",
                "resource_name": resource_name,
                "deleted_contact_name": contact_name,
            }

            # Return structured data
            yield self.create_json_message(result_data)

            # Create summary text
            summary = f"Successfully deleted contact '{contact_name}' (Resource: {resource_name})"
            yield self.create_text_message(summary)

            # Log success
            yield self.create_log_message(
                label="Contact Deleted",
                data={"resource_name": resource_name, "contact_name": contact_name},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
            )

        except requests.RequestException as e:
            yield self.create_log_message(
                label="Network Error",
                data={"error": str(e)},
                status=InvokeMessage.LogMessage.LogStatus.ERROR,
            )
            yield self.create_text_message(f"Network error occurred: {str(e)}")

        except Exception as e:
            yield self.create_log_message(
                label="Unexpected Error",
                data={"error": str(e), "type": type(e).__name__},
                status=InvokeMessage.LogMessage.LogStatus.ERROR,
            )
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
