import urllib.parse
from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.trello_client import TrelloAuthError, is_per_user, resolve_context, trello_request


class TrelloProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """Validate Trello API credentials by making a test API call.

        Args:
            credentials (dict[str, Any]): The Trello API credentials to validate.

        Raises:
            ToolProviderCredentialValidationError: If the credentials are invalid.
        """
        if is_per_user(credentials):
            self._validate_per_user(credentials)
            return
        try:
            ctx = resolve_context(credentials)
            trello_request(ctx, "GET", "members/me", params={"fields": "username"})
        except TrelloAuthError as e:
            if "401" in str(e):
                raise ToolProviderCredentialValidationError("Invalid Trello credentials: Unauthorized.") from None
            raise ToolProviderCredentialValidationError(f"Error validating Trello credentials: {e}") from None

    @staticmethod
    def _validate_per_user(credentials: dict[str, Any]) -> None:
        """No user to sign in as yet: check the fields users' sign-ins will depend on."""
        if not (credentials.get("trello_api_key") or "").strip():
            raise ToolProviderCredentialValidationError("Each user signs in needs the Trello API key.")
        if not (credentials.get("trello_api_secret") or "").strip():
            raise ToolProviderCredentialValidationError(
                "Each user signs in needs the API secret (next to the API key in the Power-Up admin portal); "
                "it encrypts the stored sign-ins."
            )
        parsed = urllib.parse.urlparse((credentials.get("redirect_uri") or "").strip())
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ToolProviderCredentialValidationError(
                "Each user signs in needs the Sign-in Callback URL: create the plugin's 'Trello sign-in' endpoint "
                "and paste its /trello/callback URL."
            )
        if (parsed.hostname or "").lower() in ("localhost", "127.0.0.1", "::1"):
            raise ToolProviderCredentialValidationError(
                "The Sign-in Callback URL points to localhost, so users' browsers cannot reach it. Replace "
                "'localhost' with your Dify domain (or set ENDPOINT_URL_TEMPLATE so Dify shows the right URL)."
            )
        if not parsed.path.endswith("/trello/callback"):
            raise ToolProviderCredentialValidationError(
                "The Sign-in Callback URL should be the 'Trello sign-in' endpoint URL ending in /trello/callback."
            )
