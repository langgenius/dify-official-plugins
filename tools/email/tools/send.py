import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

from pydantic import BaseModel


class SendEmailToolParameters(BaseModel):
    smtp_server: str
    smtp_port: int

    email_account: str
    email_password: str

    sender_to: List[str]
    subject: str
    email_content: str
    encrypt_method: str

    cc_recipients: List[str] = []
    bcc_recipients: List[str] = []


def send_mail(params: SendEmailToolParameters) -> dict[str, tuple[int, bytes]]:
    timeout = 60
    msg = MIMEMultipart("alternative")
    msg["From"] = params.email_account
    recipients_to = params.sender_to
    cc = params.cc_recipients
    bcc = params.bcc_recipients
    msg["To"] = ", ".join(recipients_to)
    if cc:
        msg["CC"] = ", ".join(cc)
    msg["Subject"] = params.subject
    msg.attach(MIMEText(params.email_content, "plain"))
    msg.attach(MIMEText(params.email_content, "html"))
    all_recipients = recipients_to + cc + bcc

    ctx = ssl.create_default_context()

    if params.encrypt_method.upper() == "SSL":
        with smtplib.SMTP_SSL(params.smtp_server, params.smtp_port, context=ctx, timeout=timeout) as server:
            server.login(params.email_account, params.email_password)
            return server.sendmail(params.email_account, all_recipients, msg.as_string())
    else:  # NONE or TLS
        with smtplib.SMTP(params.smtp_server, params.smtp_port, timeout=timeout) as server:
            if params.encrypt_method.upper() == "TLS":
                server.starttls(context=ctx)
            server.login(params.email_account, params.email_password)
            return server.sendmail(params.email_account, all_recipients, msg.as_string())
