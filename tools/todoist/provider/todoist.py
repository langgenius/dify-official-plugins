from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.auth import get_client


class TodoistProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:

            client = get_client(credentials)
            projects_iterator = client.get_projects(limit=1)
            _ = next(projects_iterator, None)

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
