from typing import Any
from tools.send_mail import SendMailTool
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

class SmtpProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in SendMailTool.from_credentials(credentials, user_id="").invoke(
                tool_parameters={
                    "subject": "Email setup",
                    "email_content": "Email setup successful",
                    "send_to": credentials.get("email_account")
                }
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
