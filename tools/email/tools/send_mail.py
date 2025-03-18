import re
from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.send import SendEmailToolParameters, send_mail
from dify_plugin import Tool


class SendMailTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        sender = self.runtime.credentials.get("email_account", "")
        email_rgx = re.compile("^[a-zA-Z0-9._-]+@[a-zA-Z0-9_-]+(\\.[a-zA-Z0-9_-]+)+$")
        password = self.runtime.credentials.get("email_password", "")
        smtp_server = self.runtime.credentials.get("smtp_server", "")
        if not smtp_server:
            yield self.create_text_message("please input smtp server")
        smtp_port = self.runtime.credentials.get("smtp_port", "")
        try:
            smtp_port = int(smtp_port)
        except ValueError:
            yield self.create_text_message("Invalid parameter smtp_port(should be int)")
        if not sender:
            yield self.create_text_message("please input sender")
        if not email_rgx.match(sender):
            yield self.create_text_message("Invalid parameter userid, the sender is not a mailbox")
        receiver_email = tool_parameters["send_to"]
        if not receiver_email:
            yield self.create_text_message("please input receiver email")
        if not email_rgx.match(receiver_email):
            yield self.create_text_message("Invalid parameter receiver email, the receiver email is not a mailbox")
        email_content = tool_parameters.get("email_content", "")
        if not email_content:
            yield self.create_text_message("please input email content")
        subject = tool_parameters.get("subject", "")
        if not subject:
            yield self.create_text_message("please input email subject")
        encrypt_method = self.runtime.credentials.get("encrypt_method", "")
        if not encrypt_method:
            yield self.create_text_message("please input encrypt method")
        send_email_params = SendEmailToolParameters(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            email_account=sender,
            email_password=password,
            sender_to=receiver_email,
            subject=subject,
            email_content=email_content,
            encrypt_method=encrypt_method,
        )
        if send_mail(send_email_params):
            yield self.create_text_message("send email success")
        yield self.create_text_message("send email failed")
