import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email import encoders

from pydantic import BaseModel
from typing import List, Optional
from dify_plugin.file.file import File


class SendEmailToolParameters(BaseModel):
    smtp_server: str
    smtp_port: int

    email_account: str
    email_password: str

    sender_to: str
    subject: str
    email_content: str
    encrypt_method: str
    
    is_html: bool = False
    plain_text_content: Optional[str] = None
    attachments: Optional[List[File]] = None


def send_mail(params: SendEmailToolParameters):
    timeout = 60
    
    # Create multipart message with mixed type to support attachments
    msg = MIMEMultipart("mixed")
    
    # Create alternative part for plain text and HTML
    alt_part = MIMEMultipart("alternative")
    
    msg["From"] = params.email_account
    msg["To"] = params.sender_to
    msg["Subject"] = params.subject
    
    # Use plain_text_content if it exists and HTML is enabled, otherwise use email_content
    plain_text = params.plain_text_content if params.is_html and params.plain_text_content else params.email_content
    
    # Always attach the plain text part
    alt_part.attach(MIMEText(plain_text, "plain"))
    
    # Only attach HTML part if HTML is enabled
    if params.is_html:
        alt_part.attach(MIMEText(params.email_content, "html"))
    
    # Add the alternative part to the main message
    msg.attach(alt_part)
    
    # Handle file attachments if any
    if params.attachments:
        for attachment in params.attachments:
            # Get file content as bytes
            file_data = attachment.blob
            
            # Get filename from file metadata or use a default name
            filename = getattr(attachment, 'filename', 'attachment')
            
            # Create attachment part
            part = MIMEApplication(file_data)
            part.add_header('Content-Disposition', 'attachment', filename=filename)
            msg.attach(part)

    ctx = ssl.create_default_context()

    if params.encrypt_method.upper() == "SSL":
        try:
            with smtplib.SMTP_SSL(params.smtp_server, params.smtp_port, context=ctx, timeout=timeout) as server:
                server.login(params.email_account, params.email_password)
                server.sendmail(params.email_account, params.sender_to, msg.as_string())
                return True
        except Exception as e:
            logging.exception(f"send email failed: {str(e)}")
            return False
    else:  # NONE or TLS
        try:
            with smtplib.SMTP(params.smtp_server, params.smtp_port, timeout=timeout) as server:
                if params.encrypt_method.upper() == "TLS":
                    server.starttls(context=ctx)
                server.login(params.email_account, params.email_password)
                server.sendmail(params.email_account, params.sender_to, msg.as_string())
                return True
        except Exception as e:
            logging.exception(f"send email failed: {str(e)}")
            return False
