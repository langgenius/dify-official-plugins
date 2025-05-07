from typing import Any

from atlassian.jira import Jira
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class JiraProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            jira_url = credentials.get("jira_url")
            username = credentials.get("username")
            api_token = credentials.get("api_token")

            if not jira_url or not username or not api_token:
                raise ToolProviderCredentialValidationError(
                    "Missing required credentials."
                )

            jira = Jira(
                url=jira_url,
                username=username,
                password=api_token,
            )

            _ = jira.projects()

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
