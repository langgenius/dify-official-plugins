import json
import re
from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.file.file import File
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.markdown_utils import convert_markdown_to_html

from tools.send import SendEmailToolParameters, send_mail


class SendMailTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        sender = self.runtime.credentials.get("email_account", "")

        sender_address = self.runtime.credentials.get("sender_address", sender) or sender

        reply_to_address = tool_parameters.get("reply_to", "")

        email_rgx = re.compile("^[a-zA-Z0-9._-]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$")
        password = self.runtime.credentials.get("email_password", "")
        smtp_server = self.runtime.credentials.get("smtp_server", "")
        if not smtp_server:
            yield self.create_text_message("please input smtp server")
            return

        smtp_port = self.runtime.credentials.get("smtp_port", "")
        try:
            smtp_port = int(smtp_port)
        except ValueError:
            yield self.create_text_message("Invalid parameter smtp_port(should be int)")
            return

        if not sender:
            yield self.create_text_message("please input sender")
            return

        if not email_rgx.match(sender_address):
            yield self.create_text_message("Invalid parameter userid, the sender is not a mailbox")
            return

        if reply_to_address and not email_rgx.match(reply_to_address):
            yield self.create_text_message(
                "Invalid parameter reply_to_address, the value is not a valid email address"
            )
            return

        receiver_email = tool_parameters["send_to"]
        if not receiver_email:
            yield self.create_text_message("please input receiver email")
            return

        if not email_rgx.match(receiver_email):
            yield self.create_text_message("Invalid parameter receiver email, the receiver email is not a mailbox")
            return

        email_content = tool_parameters.get("email_content", "")
        if not email_content:
            yield self.create_text_message("please input email content")
            return

        subject = tool_parameters.get("subject", "")
        if not subject:
            yield self.create_text_message("please input email subject")
            return

        encrypt_method = self.runtime.credentials.get("encrypt_method", "")
        if not encrypt_method:
            yield self.create_text_message("please input encrypt method")
            return

        cc_email = tool_parameters.get('cc', '')
        cc_email_list = []
        if cc_email:
            cc_email_list = json.loads(cc_email)
            for cc_email_item in cc_email_list:
                if not email_rgx.match(cc_email_item):
                    yield self.create_text_message(
                        f"Invalid parameter cc email, the cc email({cc_email_item}) is not a mailbox"
                    )
                    return

        # Process BCC recipients

        bcc_email = tool_parameters.get('bcc', '')
        bcc_email_list = []
        if bcc_email:
            bcc_email_list = json.loads(bcc_email)
            for bcc_email_item in bcc_email_list:
                if not email_rgx.match(bcc_email_item):
                    yield self.create_text_message(
                        f"Invalid parameter bcc email, the bcc email({bcc_email_item}) is not a mailbox"
                    )
                    return

        # Check if markdown to HTML conversion is requested
        convert_to_html = tool_parameters.get("convert_to_html", False)

        # Store original plain text content before any conversion
        plain_text_content = email_content

        if convert_to_html:
            # Convert content to HTML using shared utility
            email_content, plain_text_content = convert_markdown_to_html(email_content)

        # Get attachments from parameters (if any)
        attachments = tool_parameters.get("attachments", None)

        # Convert single attachment to list if needed
        if attachments is not None and not isinstance(attachments, list):
            attachments = [attachments]

        # Create email parameters object with all fields

        send_email_params = SendEmailToolParameters(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            email_account=sender,
            email_password=password,
            sender_address=sender_address,
            sender_to=[receiver_email],
            subject=subject,
            email_content=email_content,
            encrypt_method=encrypt_method,
            is_html=convert_to_html,
            plain_text_content=plain_text_content if convert_to_html else None,
            attachments=attachments,
            cc_recipients=cc_email_list,
            bcc_recipients=bcc_email_list,
            reply_to_address=reply_to_address
        )

        # Prepare response message
        msg = {}
        for receiver in [receiver_email] + cc_email_list + bcc_email_list:
            msg[receiver] = "send email success"

        # Send the email and get result
        result = send_mail(send_email_params)

        # Process results
        if result:
            for key, (integer_value, bytes_value) in result.items():
                msg[key] = f"send email failed: {integer_value} {bytes_value.decode('utf-8')}"

        # Add attachment information to the response message
        response_text = json.dumps(msg)
        if attachments:
            attachment_count = len(attachments)
            yield self.create_text_message(
                f"Email sent with {attachment_count} attachment(s). Details: {response_text}"
            )
        else:
            yield self.create_text_message(response_text)

