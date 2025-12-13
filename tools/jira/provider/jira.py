from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.auth import auth


class JiraProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            jira = auth(credentials)
            projects = jira.projects()

        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Jira authentication failed: {e}"
            )
