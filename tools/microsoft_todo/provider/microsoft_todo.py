# import structlog

# log = structlog.get_logger()
import json
from typing import Any, Mapping

from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import (
    ToolProviderCredentialValidationError,
    ToolProviderOAuthError,
)
from pymstodo import ToDoConnection
from pymstodo.client import Token
from requests_oauthlib import OAuth2Session
from werkzeug import Request


class MicrosoftTodoProvider(ToolProvider):

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        # log.debug(f"Redirect URI: {redirect_uri}")
        # log.debug(f"System Credentials: {system_credentials}")

        client_id = system_credentials.get("client_id")
        if not client_id:
            raise ToolProviderCredentialValidationError(
                "Client ID is required for OAuth."
            )

        ToDoConnection._redirect = redirect_uri

        return ToDoConnection.get_auth_url(client_id)

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        # log.debug(f"Redirect URI: {redirect_uri}")
        # log.debug(f"System Credentials: {system_credentials}")

        code = request.args.get("code")
        if not code:
            raise ToolProviderCredentialValidationError(
                "Authorization code is missing in the request."
            )

        ToDoConnection._redirect = redirect_uri
        token_url = f"{ToDoConnection._authority}{ToDoConnection._token_endpoint}"

        oa_sess = OAuth2Session(
            system_credentials["client_id"],
            scope=ToDoConnection._scope,
            redirect_uri=ToDoConnection._redirect,
        )

        token: dict[str, Any] = oa_sess.fetch_token(
            token_url,
            client_secret=system_credentials["client_secret"],
            code=code,
        )

        credentials = ToolOAuthCredentials(
            credentials={
                "token": json.dumps(token),
                "client_id": system_credentials["client_id"],
                "client_secret": system_credentials["client_secret"],
            },
            expires_at=token.get("expires_at"),
        )
        # log.debug(f"Original token expires_at: {token.get('expires_at')}")
        # log.debug(f"[Fake] Credentials expires_at: {credentials.expires_at}")
        return credentials

    # def _oauth_refresh_credentials(
    #     self,
    #     redirect_uri: str,
    #     system_credentials: Mapping[str, Any],
    #     credentials: Mapping[str, Any],
    # ) -> ToolOAuthCredentials:

    #     todo_client = ToDoConnection(
    #         client_id=system_credentials["client_id"],
    #         client_secret=system_credentials["client_secret"],
    #         token=Token(**json.loads(credentials["token"])),
    #     )

    #     todo_client._refresh_token()

    #     return ToolOAuthCredentials(
    #         credentials={
    #             "token": json.dumps(todo_client.token),
    #             "client_id": system_credentials["client_id"],
    #             "client_secret": system_credentials["client_secret"],
    #         },
    #         expires_at=todo_client.token.get("expires_at"),
    #     )

    def _oauth_refresh_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        credentials: Mapping[str, Any],
    ) -> ToolOAuthCredentials:
        # log.debug(f"Redirect URI: {redirect_uri}")
        # log.debug(f"System Credentials: {system_credentials}")

        ToDoConnection._redirect = redirect_uri
        token_url = f"{ToDoConnection._authority}{ToDoConnection._token_endpoint}"
        token = json.loads(credentials["token"])

        # log.debug(f"Before refresh, Credentials Expires at: {token.get('expires_at')}")

        refresh_token = token["refresh_token"]
        oa_sess = OAuth2Session(
            system_credentials["client_id"],
            scope=ToDoConnection._scope,
            redirect_uri=ToDoConnection._redirect,
        )
        try:
            new_token = oa_sess.refresh_token(
                token_url,
                refresh_token=refresh_token,
                client_id=system_credentials["client_id"],
                client_secret=system_credentials["client_secret"],
            )
            expires_at = new_token["expires_at"]

            # log.debug(f"New token expires at: {expires_at}")

            token_str = json.dumps(new_token)
            return ToolOAuthCredentials(
                credentials={"token": token_str}, expires_at=expires_at
            )
        except Exception as e:
            raise ToolProviderOAuthError(str(e)) from e

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:

        try:
            token: Token = Token(**json.loads(credentials["token"]))
            if not token.access_token:
                raise ToolProviderCredentialValidationError("Access token is missing.")

            todo_client = ToDoConnection(
                client_id=credentials["client_id"],
                client_secret=credentials["client_secret"],
                token=token,
            )

            lists = todo_client.get_lists()
            raise Exception(
                f"token: {token}\n" f"lists: {lists}\n" f"credentials: {credentials}"
            )

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
