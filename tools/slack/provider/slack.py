from typing import Any

import requests

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class SlackProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            client = SlackClient(credentials)
        except SlackConfigError as e:
            raise ToolProviderCredentialValidationError(str(e))

        # auth.test confirms the bot token is valid and reveals the workspace.
        try:
            response = client.call("auth.test", http_method="POST")
        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Could not reach the Slack API: {e}"
            )

        ok, _, error = slack_result(response)
        if not ok:
            raise ToolProviderCredentialValidationError(
                f"Invalid Slack Bot Token: {error}"
            )

        # If a user token was supplied, validate it too.
        user_token = (credentials.get("slack_user_token") or "").strip()
        if user_token:
            try:
                user_client = SlackClient(credentials, require_user_token=True)
                response = user_client.call("auth.test", http_method="POST")
            except requests.exceptions.RequestException as e:
                raise ToolProviderCredentialValidationError(
                    f"Could not validate the User Token: {e}"
                )
            ok, _, error = slack_result(response)
            if not ok:
                raise ToolProviderCredentialValidationError(
                    f"Invalid Slack User Token: {error}"
                )
