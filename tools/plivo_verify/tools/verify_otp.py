from typing import Any, Generator

import plivo
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class VerifyOtpTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        session_id = tool_parameters["session_id"].strip()
        otp_code = tool_parameters["otp_code"].strip()

        auth_id = self.runtime.credentials["auth_id"]
        auth_token = self.runtime.credentials["auth_token"]

        try:
            client = plivo.RestClient(auth_id=auth_id, auth_token=auth_token)
            response = client.verify_session.validate(
                session_uuid=session_id,
                otp=otp_code,
            )
            # Plivo returns status field indicating verification result
            # Successful validation typically has no error
            verified = True
        except plivo.exceptions.AuthenticationError:
            yield self.create_text_message("Plivo authentication failed. Please check your credentials.")
            return
        except plivo.exceptions.ValidationError as e:
            # Invalid OTP or expired session
            yield self.create_text_message(f"OTP verification failed: {e}")
            yield self.create_json_message({
                "status": "failed",
                "verified": False,
                "session_id": session_id,
                "error": str(e),
            })
            return
        except plivo.exceptions.PlivoRestError as e:
            error_str = str(e).lower()
            # Check if this is an invalid OTP error vs other API errors
            if "invalid" in error_str or "incorrect" in error_str or "expired" in error_str:
                yield self.create_text_message(f"OTP verification failed: {e}")
                yield self.create_json_message({
                    "status": "failed",
                    "verified": False,
                    "session_id": session_id,
                    "error": str(e),
                })
                return
            yield self.create_text_message(f"Plivo API error: {e}")
            return
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {e}")
            return

        yield self.create_text_message(
            f"OTP verified successfully for session {session_id}."
        )
        yield self.create_json_message({
            "status": "success",
            "verified": verified,
            "session_id": session_id,
        })
