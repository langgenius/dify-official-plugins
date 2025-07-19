import json
from pprint import pprint as debug_print
from typing import Any, Mapping

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from pymstodo import ToDoConnection
from pymstodo.client import Token
from requests_oauthlib import OAuth2Session
from werkzeug import Request


class MicrosoftTodoProvider(ToolProvider):

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        debug_print(f"Redirect URI: {redirect_uri}")
        debug_print(f"System Credentials: {system_credentials}")

        client_id = system_credentials.get("client_id")
        if not client_id:
            raise ToolProviderCredentialValidationError(
                "Client ID is required for OAuth."
            )

        ToDoConnection._redirect = redirect_uri

        return ToDoConnection.get_auth_url(client_id)

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> Mapping[str, Any]:
        debug_print(f"Redirect URI: {redirect_uri}")
        debug_print(f"System Credentials: {system_credentials}")

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

        return {
            "token": json.dumps(
                oa_sess.fetch_token(
                    token_url,
                    client_secret=system_credentials["client_secret"],
                    code=code,
                )
            )
        }

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        debug_print(f"Validating credentials: {credentials}")

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
            debug_print(f"Retrieved lists: {lists}")
            raise Exception(
                f"token: {token}\n" f"lists: {lists}\n" f"credentials: {credentials}"
            )

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
