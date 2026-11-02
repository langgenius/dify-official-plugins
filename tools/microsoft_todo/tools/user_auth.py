"""
"Each user signs in" mode: every chat user acts with their own Microsoft account.

The workspace credential only holds the app registration (tenant, client ID, client
secret, cloud) and the URL of this plugin's sign-in callback endpoint. A user's
token is obtained the first time a tool needs it:

1. the tool finds no token for ``runtime.user_id``, saves a pending sign-in (random
   state + PKCE verifier) and returns the Microsoft sign-in link as its result, so
   the agent can hand it to the user;
2. Microsoft redirects the browser to the callback endpoint, which only stores the
   authorization code under its state (it holds no secret and cannot redeem it);
3. on the user's next request the tool redeems the code with the client secret and
   the PKCE verifier and keeps the token in plugin storage.

Everything stored per user is encrypted with a key derived from the client secret,
so plugin storage alone does not reveal a token, and rotating the secret signs
everybody out. Tokens never appear in tool output.
"""

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from typing import Any, Mapping

import requests
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# The OAuth credential's permissions (MicrosoftTodoProvider._SCOPE), plus User.Read so the
# signed-in account can be named.
DELEGATED_SCOPE = "openid offline_access User.Read Tasks.ReadWrite"

# A sign-in link stays usable this long; Entra's authorization codes live ~10 minutes.
_PENDING_TTL = 15 * 60
# Refresh an access token this many seconds before it expires.
_EXPIRY_MARGIN = 120

# Storage keys: per-user state under user/<hash>, callback codes under signin/<state>.
_STATE_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


class SignInRequired(Exception):
    """The current user has to (finish) signing in; the message carries the link for them."""


class UserAuthError(Exception):
    """Per-user sign-in is misconfigured or Microsoft rejected it."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def is_valid_state(state: str) -> bool:
    return 20 <= len(state) <= 64 and set(state) <= _STATE_CHARS


def signin_key(state: str) -> str:
    return f"signin/{state}"


def code_key(state: str) -> str:
    return f"signin/{state}.code"


def _user_key(credentials: Mapping[str, Any], user_id: str, name: str) -> str:
    # Scoped to the app registration so switching apps never reuses another app's tokens.
    digest = hashlib.sha256(f"{credentials.get('client_id', '')}|{user_id}".encode()).hexdigest()
    return f"user/{digest}/{name}"


def _fernet(credentials: Mapping[str, Any]) -> Fernet:
    secret = (credentials.get("client_secret") or "").encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"dify-todo-per-user-token").derive(secret)
    return Fernet(base64.urlsafe_b64encode(key))


class UserTokenStore:
    """Encrypted per-user records in plugin storage (``session.storage``)."""

    def __init__(self, storage: Any, credentials: Mapping[str, Any], user_id: str):
        self._storage = storage
        self._credentials = credentials
        self._user_id = user_id
        self._fernet = _fernet(credentials)

    def load(self, name: str) -> dict[str, Any] | None:
        key = _user_key(self._credentials, self._user_id, name)
        if not self._storage.exist(key):
            return None
        try:
            return json.loads(self._fernet.decrypt(self._storage.get(key)))
        except (InvalidToken, ValueError):
            # Written with another client secret: treat as signed out.
            self._storage.delete(key)
            return None

    def save(self, name: str, value: Mapping[str, Any]) -> None:
        key = _user_key(self._credentials, self._user_id, name)
        self._storage.set(key, self._fernet.encrypt(json.dumps(value).encode()))

    def delete(self, name: str) -> None:
        key = _user_key(self._credentials, self._user_id, name)
        if self._storage.exist(key):
            self._storage.delete(key)


def _scope(graph_host: str, global_graph_host: str) -> str:
    """Outside the global cloud each permission is qualified with that cloud's Graph host."""
    if graph_host == global_graph_host:
        return DELEGATED_SCOPE
    return " ".join(
        item if item in ("offline_access", "openid", "profile", "email") else f"{graph_host}/{item}" for item in DELEGATED_SCOPE.split()
    )


class UserSignIn:
    """Get a delegated Graph token for one chat user, starting a sign-in when there is none."""

    def __init__(
        self,
        credentials: Mapping[str, Any],
        user_id: str | None,
        storage: Any,
        login_host: str,
        graph_host: str,
        global_graph_host: str,
    ):
        if not user_id:
            raise UserAuthError(
                "This credential uses per-user sign-in, but Dify did not say which user is calling the tool."
            )
        self.credentials = credentials
        self.storage = storage
        self.store = UserTokenStore(storage, credentials, user_id)
        self.graph_host = graph_host
        tenant = (credentials.get("tenant_id") or "organizations").strip()
        self.authorize_url = f"{login_host}/{tenant}/oauth2/v2.0/authorize"
        self.token_url = f"{login_host}/{tenant}/oauth2/v2.0/token"
        self.scope = _scope(graph_host, global_graph_host)
        self.redirect_uri = (credentials.get("redirect_uri") or "").strip()
        # Set when this call finished a sign-in: the account the user signed in with.
        self.just_signed_in: str | None = None
        if not self.redirect_uri:
            raise UserAuthError(
                "Per-user sign-in needs the Sign-in Callback URL: create the plugin's 'To Do sign-in' "
                "endpoint and paste its URL into the credential."
            )

    def access_token(self) -> str:
        token = self.store.load("token")
        if token is None:
            token = self._finish_pending_sign_in()
        if token["expires_at"] - _EXPIRY_MARGIN > time.time():
            return token["access_token"]
        return self._refresh(token)

    def sign_out(self) -> bool:
        had_token = self.store.load("token") is not None
        pending = self.store.load("pending")
        if pending:
            self._forget_state(pending["state"])
        self.store.delete("token")
        self.store.delete("pending")
        return had_token

    # ── sign-in ───────────────────────────────────────────────────────

    def _finish_pending_sign_in(self) -> dict[str, Any]:
        pending = self.store.load("pending")
        if pending is None or pending["expires_at"] < time.time():
            if pending:
                self._forget_state(pending["state"])
            raise SignInRequired(self._start_sign_in())

        callback = self._take_code(pending["state"])
        if callback is None:
            raise SignInRequired(
                "Sign-in has not been completed yet. Ask the user to open this link, sign in with their "
                f"Microsoft account, then tell you when they are done:\n{pending['url']}"
            )
        self.store.delete("pending")
        self._forget_state(pending["state"])
        if callback.get("error"):
            raise UserAuthError(f"Microsoft sign-in failed: {callback['error']}. Ask the user to try again.")

        payload = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": callback["code"],
                "redirect_uri": self.redirect_uri,
                "code_verifier": pending["verifier"],
                "scope": self.scope,
            }
        )
        account = self._account_name(payload["access_token"]) if payload.get("access_token") else None
        self.just_signed_in = account or "an unknown account"
        return self._store_token(payload, account=account)

    def _account_name(self, access_token: str) -> str | None:
        """The signed-in user's sign-in name, so the user can spot a wrong account; best effort."""
        try:
            response = requests.get(
                f"{self.graph_host}/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"$select": "userPrincipalName,mail"},
                timeout=15,
            )
            if response.status_code == 200:
                me = response.json()
                return me.get("userPrincipalName") or me.get("mail")
        except (requests.exceptions.RequestException, ValueError):
            pass
        return None

    def account(self) -> str | None:
        token = self.store.load("token")
        return token.get("account") if token else None

    def _start_sign_in(self) -> str:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        url = f"{self.authorize_url}?" + urllib.parse.urlencode(
            {
                "client_id": self.credentials.get("client_id", ""),
                "response_type": "code",
                "redirect_uri": self.redirect_uri,
                "response_mode": "query",
                "scope": self.scope,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        expires_at = time.time() + _PENDING_TTL
        self.store.save("pending", {"state": state, "verifier": verifier, "url": url, "expires_at": expires_at})
        # Lets the callback endpoint tell a link it issued from a forged or expired one.
        self.storage.set(signin_key(state), json.dumps({"expires_at": expires_at}).encode())
        return (
            "The user has not signed in to Microsoft yet. Give them this link to sign in with their own "
            "Microsoft account (valid for 15 minutes), and call this tool again after they say they are done:\n"
            f"{url}"
        )

    def _take_code(self, state: str) -> dict[str, Any] | None:
        key = code_key(state)
        if not self.storage.exist(key):
            return None
        try:
            return json.loads(self.storage.get(key))
        except ValueError:
            return {"error": "the sign-in response could not be read"}

    def _forget_state(self, state: str) -> None:
        for key in (signin_key(state), code_key(state)):
            if self.storage.exist(key):
                self.storage.delete(key)

    # ── tokens ────────────────────────────────────────────────────────

    def _refresh(self, token: Mapping[str, Any]) -> str:
        if not token.get("refresh_token"):
            self.store.delete("token")
            raise SignInRequired(self._start_sign_in())
        try:
            payload = self._token_request(
                {"grant_type": "refresh_token", "refresh_token": token["refresh_token"], "scope": self.scope}
            )
        except UserAuthError as e:
            if e.status not in (400, 401):
                raise
            # Refresh token revoked, expired after inactivity, password changed...: sign in again.
            self.store.delete("token")
            raise SignInRequired(self._start_sign_in()) from e
        return self._store_token(payload, token["refresh_token"], token.get("account"))["access_token"]

    def _store_token(
        self, payload: Mapping[str, Any], previous_refresh_token: str | None = None, account: str | None = None
    ) -> dict[str, Any]:
        if not payload.get("access_token"):
            raise UserAuthError("Microsoft returned no access token.")
        token = {
            "access_token": payload["access_token"],
            # Entra normally rotates the refresh token; keep the old one if a response omits it.
            "refresh_token": payload.get("refresh_token") or previous_refresh_token,
            "expires_at": time.time() + int(payload.get("expires_in", 3599)),
            "account": account,
        }
        self.store.save("token", token)
        return token

    def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        data |= {
            "client_id": self.credentials.get("client_id", ""),
            "client_secret": self.credentials.get("client_secret", ""),
        }
        try:
            response = requests.post(self.token_url, data=data, timeout=30)
        except requests.exceptions.RequestException as e:
            raise UserAuthError(f"Could not reach Microsoft Entra ID: {e}") from e
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code != 200:
            detail = payload.get("error_description") or payload.get("error") or response.text[:300]
            raise UserAuthError(f"Microsoft sign-in failed ({response.status_code}): {detail}", response.status_code)
        return payload
