from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class FlagMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # Get parameters
            message_id = tool_parameters.get("message_id")
            action = tool_parameters.get("action", "flag").lower()
            
            if not message_id:
                yield self.create_text_message("Error: Message ID is required.")
                return
            
            if action not in ["flag", "unflag"]:
                yield self.create_text_message("Error: Action must be either 'flag' or 'unflag'.")
                return
            
            # Get credentials from tool provider
            access_token = self.runtime.credentials.get("access_token")
            
            if not access_token:
                yield self.create_text_message("Error: No access token available. Please authorize the Gmail integration.")
                return
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            # Determine which labels to add/remove
            if action == "flag":
                # Add the starred label
                labels_to_add = ["STARRED"]
                labels_to_remove = []
                action_text = "flagging"
            else:
                # Remove the starred label
                labels_to_add = []
                labels_to_remove = ["STARRED"]
                action_text = "unflagging"
            
            # Prepare the request body
            request_body = {
                "addLabelIds": labels_to_add,
                "removeLabelIds": labels_to_remove
            }
            
            yield self.create_text_message(f"{action_text.title()} message {message_id}...")
            
            # Modify the message labels
            modify_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify"
            
            response = requests.post(
                modify_url,
                headers=headers,
                json=request_body,
                timeout=30
            )
            
            if response.status_code == 401:
                yield self.create_text_message("Error: Access token expired. Please re-authorize the Gmail integration.")
                return
            elif response.status_code == 404:
                yield self.create_text_message("Error: Message not found. The message ID may be invalid or the message may have been deleted.")
                return
            elif response.status_code != 200:
                yield self.create_text_message(f"Error: Gmail API returned status {response.status_code}: {response.text}")
                return
            
            # Parse response
            response_data = response.json()
            updated_labels = response_data.get("labelIds", [])
            
            # Check if the action was successful
            if action == "flag":
                if "STARRED" in updated_labels:
                    success_message = "Message flagged successfully for follow-up!"
                else:
                    success_message = "Warning: Message may not have been flagged properly."
            else:
                if "STARRED" not in updated_labels:
                    success_message = "Message unflagged successfully!"
                else:
                    success_message = "Warning: Message may not have been unflagged properly."
            
            # Return success results
            yield self.create_text_message(success_message)
            yield self.create_json_message({
                "status": "success",
                "message_id": message_id,
                "action": action,
                "updated_labels": updated_labels,
                "is_starred": "STARRED" in updated_labels
            })
            
        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error {action}ing message: {str(e)}") 