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

            # Log-in with E-Mail / Username and regular password
            # or with Username and App password.
            # Get App password from https://bitbucket.org/account/settings/app-passwords/.
            # Log-in with E-Mail and App password not possible.
            # Username can be found here: https://bitbucket.org/account/settings/

            bitbucket = Cloud(
                url=credentials.get("bitbucket_url", "https://api.bitbucket.org"),
                username=credentials.get("username"),
                password=credentials.get("password"),
            )

            next(bitbucket.workspaces.each())

        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to validate Bitbucket credentials. Error: {e}"
            )
