import smtplib
import ssl
from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class SmtpProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validate SMTP credentials by attempting to login to the SMTP server.
        """
        smtp_server = credentials.get("smtp_server", "")
        smtp_port = credentials.get("smtp_port", "")
        email_account = credentials.get("email_account", "")
        email_password = credentials.get("email_password", "")
        encrypt_method = credentials.get("encrypt_method", "SSL")

        if not smtp_server:
            raise ToolProviderCredentialValidationError("SMTP server is required")
        if not smtp_port:
            raise ToolProviderCredentialValidationError("SMTP port is required")
        if not email_account:
            raise ToolProviderCredentialValidationError("Email account is required")
        if not email_password:
            raise ToolProviderCredentialValidationError("Email password is required")

        try:
            smtp_port = int(smtp_port)
        except ValueError:
            raise ToolProviderCredentialValidationError("SMTP port must be a valid number")

        timeout = 30
        ctx = ssl.create_default_context()

        try:
            if encrypt_method.upper() == "SSL":
                with smtplib.SMTP_SSL(smtp_server, smtp_port, context=ctx, timeout=timeout) as server:
                    server.login(email_account, email_password)
            else:  # NONE or TLS
                with smtplib.SMTP(smtp_server, smtp_port, timeout=timeout) as server:
                    if encrypt_method.upper() == "TLS":
                        server.starttls(context=ctx)
                    server.login(email_account, email_password)
        except smtplib.SMTPAuthenticationError as e:
            raise ToolProviderCredentialValidationError(f"Authentication failed: {str(e)}")
        except smtplib.SMTPConnectError as e:
            raise ToolProviderCredentialValidationError(f"Failed to connect to SMTP server: {str(e)}")
        except smtplib.SMTPException as e:
            raise ToolProviderCredentialValidationError(f"SMTP error: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Failed to validate credentials: {str(e)}")
