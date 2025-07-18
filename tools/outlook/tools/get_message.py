import asyncio
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient

class GetMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get a specific message from Outlook
        """
        try:
            # Get parameters
            message_id = tool_parameters.get("message_id")
            user_email = self.runtime.credentials.get("user_email")
            
            # Validate parameters
            if not message_id:
                yield self.create_text_message("Message ID is required.")
                return
                
            if not user_email:
                yield self.create_text_message("User email is required in credentials.")
                return
                
            # Get credentials
            client_id = self.runtime.credentials.get("client_id")
            client_secret = self.runtime.credentials.get("client_secret")
            tenant_id = self.runtime.credentials.get("tenant_id")
            
            if not all([client_id, client_secret, tenant_id]):
                yield self.create_text_message("Azure AD credentials are required.")
                return
                
            # Create credential and client
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
            graph_client = GraphServiceClient(credentials=credential)
            
            # Get message
            message = asyncio.run(graph_client.users.by_user_id(user_email).messages.by_message_id(message_id).get())
            
            if not message:
                yield self.create_text_message("Message not found.")
                return
                
            # Format response
            result = {
                "id": message.id,
                "subject": message.subject,
                "sender": message.sender.email_address.address,
                "to_recipients": [r.email_address.address for r in message.to_recipients],
                "cc_recipients": [r.email_address.address for r in message.cc_recipients] if message.cc_recipients else [],
                "received": message.received_date_time,
                "body": message.body.content,
                "body_type": message.body.content_type,
                "has_attachments": message.has_attachments
            }
            
            # Get attachments if any
            if message.has_attachments:
                attachments = graph_client.users.by_user_id(user_email).messages.by_message_id(message_id).attachments.get()
                result["attachments"] = [{
                    "id": a.id,
                    "name": a.name,
                    "content_type": a.content_type,
                    "size": a.size
                } for a in attachments.value]
                
            # Create response
            yield self.create_text_message(f"Retrieved message: {message.subject}")
            yield self.create_json_message(result)
            
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return 