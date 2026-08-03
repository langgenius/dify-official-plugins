from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from slack_api import SlackApiError, SlackClient


class SlackProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        access_token = credentials.get("access_token")
        if not access_token:
            raise ToolProviderCredentialValidationError(
                "Slack Access Token (access_token) is required."
            )
        try:
            SlackClient(access_token).auth_test()
        except SlackApiError as e:
            raise ToolProviderCredentialValidationError(
                f"Invalid Slack Access Token: {e.slack_error}"
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
