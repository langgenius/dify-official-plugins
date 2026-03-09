from typing import Any, Generator

import plivo
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SendOtpTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        phone_number = tool_parameters["phone_number"].strip()
        channel = tool_parameters.get("channel", "sms").strip().lower()
        app_uuid = tool_parameters.get("app_uuid", "").strip() or None

        auth_id = self.runtime.credentials["auth_id"]
        auth_token = self.runtime.credentials["auth_token"]

        try:
            client = plivo.RestClient(auth_id=auth_id, auth_token=auth_token)
            create_params = {
                "recipient": phone_number,
                "channel": channel,
            }
            if app_uuid:
                create_params["app_uuid"] = app_uuid
            response = client.verify_session.create(**create_params)
            session_uuid = response.session_uuid
        except plivo.exceptions.AuthenticationError:
            yield self.create_text_message("Plivo authentication failed. Please check your credentials.")
            return
        except plivo.exceptions.ValidationError as e:
            yield self.create_text_message(f"Invalid request parameters: {e}")
            return
        except plivo.exceptions.PlivoRestError as e:
            yield self.create_text_message(f"Plivo API error: {e}")
            return
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {e}")
            return

        yield self.create_text_message(
            f"OTP sent successfully to {phone_number} via {channel}. Session ID: {session_uuid}"
        )
        yield self.create_json_message({
            "status": "success",
            "session_id": session_uuid,
            "phone_number": phone_number,
            "channel": channel,
        })
