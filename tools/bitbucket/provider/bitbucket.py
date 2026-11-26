from typing import Any

from atlassian.bitbucket import Cloud
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class BitbucketProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validates the provided Bitbucket credentials by attempting to connect
        and fetch the current user's information.
        """
        try:

            bitbucket = Cloud(
                url=credentials.get("bitbucket_url", "https://api.bitbucket.org"),
                username=credentials.get("username"),
                password=credentials.get("password"),
            )

            next(bitbucket.workspaces.each(), None)

        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to validate Bitbucket credentials. Use your Atlassian account email and scoped API token. Error: {e}"
            ) from e
