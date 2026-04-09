from typing import Any, Generator

import plivo
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SendSmsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        to_number = tool_parameters["to_number"].strip()
        from_number = tool_parameters["from_number"].strip()
        message_text = tool_parameters["message"].strip()

        auth_id = self.runtime.credentials["auth_id"]
        auth_token = self.runtime.credentials["auth_token"]

        try:
            client = plivo.RestClient(auth_id=auth_id, auth_token=auth_token)
            response = client.messages.create(
                src=from_number,
                dst=to_number,
                text=message_text,
            )
            message_uuid = response.message_uuid[0] if response.message_uuid else "unknown"
        except plivo.exceptions.AuthenticationError:
            yield self.create_text_message("Plivo authentication failed. Please check your credentials.")
            return
        except plivo.exceptions.ValidationError as e:
            yield self.create_text_message(f"Invalid request parameters: {e}")
            return
        except plivo.exceptions.PlivoRestError as e:
            yield self.create_text_message(f"Plivo API error: {e}")
            return

        yield self.create_text_message(
            f"SMS sent successfully to {to_number}. Message UUID: {message_uuid}"
        )
        yield self.create_json_message({
            "status": "success",
            "message_uuid": message_uuid,
            "to": to_number,
            "from": from_number,
            "message": message_text,
        })
