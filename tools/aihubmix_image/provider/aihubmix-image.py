from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from utils.client import AIHubMixClient, GatewayError


class AIHubMixImageProvider(ToolProvider):

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            client = AIHubMixClient(credentials)
            # Any authenticated endpoint proves the key; the model list is the cheapest one.
            client.get_json("/v1/models", timeout=10)
        except GatewayError as exc:
            if exc.status in (401, 403):
                raise ToolProviderCredentialValidationError("Invalid API Key") from exc
            raise ToolProviderCredentialValidationError(str(exc)) from exc

    #########################################################################################
    # OAuth support can be implemented by uncommenting the following functions.
    # Note: Ensure SDK version is 0.4.2 or higher for OAuth functionality.
    #########################################################################################
    # def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
    #     """
    #     Generate the authorization URL for aihubmix-image OAuth.
    #     """
    #     try:
    #         """
    #         IMPLEMENT YOUR AUTHORIZATION URL GENERATION HERE
    #         """
    #     except Exception as e:
    #         raise ToolProviderOAuthError(str(e))
    #     return ""
        
    # def _oauth_get_credentials(
    #     self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    # ) -> Mapping[str, Any]:
    #     """
    #     Exchange code for access_token.
    #     """
    #     try:
    #         """
    #         IMPLEMENT YOUR CREDENTIALS EXCHANGE HERE
    #         """
    #     except Exception as e:
    #         raise ToolProviderOAuthError(str(e))
    #     return dict()

    # def _oauth_refresh_credentials(
    #     self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    # ) -> OAuthCredentials:
    #     """
    #     Refresh the credentials
    #     """
    #     return OAuthCredentials(credentials=credentials, expires_at=-1)
