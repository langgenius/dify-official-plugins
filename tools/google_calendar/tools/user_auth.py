"""
"Each user signs in" mode: every chat user acts with their own Google account.

The workspace credential only holds the OAuth client (client ID, client secret) and the
URL of this plugin's sign-in callback endpoint. A user's token is obtained the first
time a tool needs it:

1. the tool finds no token for ``runtime.user_id``, saves a pending sign-in (random
   state + PKCE verifier) and returns the Google sign-in link as its result, so the
   agent can hand it to the user;
2. Google redirects the browser to the callback endpoint, which only stores the
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

# ── per plugin ────────────────────────────────────────────────────────
PLUGIN = "google_calendar"
PRODUCT = "Google Calendar"
# Same permission as the OAuth credential, plus openid/email to show which account signed in.
SCOPE = "openid email https://www.googleapis.com/auth/calendar"
# ──────────────────────────────────────────────────────────────────────

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# A sign-in link stays usable this long; Google's authorization codes are short-lived too.
_PENDING_TTL = 15 * 60
# Refresh an access token this many seconds before it expires.
_EXPIRY_MARGIN = 120

# Storage keys: per-user state under user/<hash>, callback codes under signin/<state>.
_STATE_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


class SignInRequired(Exception):
    """The current user has to (finish) signing in; the message carries the link for them."""


class UserAuthError(Exception):
    """Per-user sign-in is misconfigured or Google rejected it."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def is_valid_state(state: str) -> bool:
    return 20 <= len(state) <= 64 and set(state) <= _STATE_CHARS


def signin_key(state: str) -> str:
    return f"signin/{state}"


def code_key(state: str) -> str:
    return f"signin/{state}.code"


def scope(credentials: Mapping[str, Any]) -> str:
    """The scopes to request: the plugin's default, or the credential's override (plus openid/email)."""
    items = (credentials.get("scopes") or "").replace(",", " ").split() or SCOPE.split()
    for required in ("openid", "email"):
        if required not in items:
            items.insert(0, required)
    return " ".join(dict.fromkeys(items))


def _user_key(credentials: Mapping[str, Any], user_id: str, name: str) -> str:
    # Scoped to the OAuth client so switching clients never reuses another client's tokens.
    digest = hashlib.sha256(f"{credentials.get('client_id', '')}|{user_id}".encode()).hexdigest()
    return f"user/{digest}/{name}"


def _fernet(credentials: Mapping[str, Any]) -> Fernet:
    secret = (credentials.get("client_secret") or "").encode()
    info = f"dify-{PLUGIN}-per-user-token".encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(secret)
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


class UserSignIn:
    """Get a Google token for one chat user, starting a sign-in when there is none."""

    def __init__(self, credentials: Mapping[str, Any], user_id: str | None, storage: Any):
        if not user_id:
            raise UserAuthError("This credential uses per-user sign-in, but Dify did not say which user is calling the tool.")
        self.credentials = credentials
        self.storage = storage
        self.store = UserTokenStore(storage, credentials, user_id)
        self.scope = scope(credentials)
        self.redirect_uri = (credentials.get("redirect_uri") or "").strip()
        # Set when this call finished a sign-in: the account the user signed in with.
        self.just_signed_in: str | None = None
        if not self.redirect_uri:
            raise UserAuthError(
                f"Per-user sign-in needs the Sign-in Callback URL: create the plugin's '{PRODUCT} sign-in' "
                "endpoint and paste its URL into the credential."
            )

    def access_token(self) -> str:
        token = self.store.load("token")
        if token is None:
            token = self._finish_pending_sign_in()
        if token["expires_at"] - _EXPIRY_MARGIN > time.time():
            return token["access_token"]
        return self._refresh(token)

    def account(self) -> str | None:
        token = self.store.load("token")
        return token.get("account") if token else None

    def sign_out(self) -> bool:
        had_token = self.store.load("token") is not None
        pending = self.store.load("pending")
        if pending:
            self._forget_state(pending["state"])
        self.store.delete("token")
        self.store.delete("pending")
        return had_token

    def expired(self) -> str:
        """Google rejected the access token (revoked, or the consent was withdrawn): sign in again."""
        self.store.delete("token")
        return self._start_sign_in()

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
                f"Google account, then tell you when they are done:\n{pending['url']}"
            )
        self.store.delete("pending")
        self._forget_state(pending["state"])
        if callback.get("error"):
            raise UserAuthError(f"Google sign-in failed: {callback['error']}. Ask the user to try again.")

        payload = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": callback["code"],
                "redirect_uri": self.redirect_uri,
                "code_verifier": pending["verifier"],
            }
        )
        granted = set((payload.get("scope") or "").split())
        missing = [s for s in self.scope.split() if s.startswith("https://") and s not in granted]
        if granted and missing:
            # Google lets users untick permissions on the consent screen.
            raise UserAuthError(
                "The sign-in did not grant every permission this plugin needs "
                f"({', '.join(missing)}). Ask the user to sign in again and keep all boxes ticked."
            )
        account = self._account_name(payload["access_token"])
        self.just_signed_in = account or "an unknown account"
        return self._store_token(payload, account=account)

    def _account_name(self, access_token: str) -> str | None:
        """The signed-in account's email, so the user can spot a wrong account; best effort."""
        try:
            response = requests.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
            if response.status_code == 200:
                return response.json().get("email")
        except (requests.exceptions.RequestException, ValueError):
            pass
        return None

    def _start_sign_in(self) -> str:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        url = f"{AUTHORIZE_URL}?" + urllib.parse.urlencode(
            {
                "client_id": self.credentials.get("client_id", ""),
                "response_type": "code",
                "redirect_uri": self.redirect_uri,
                "scope": self.scope,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                # offline + consent: Google only returns a refresh token on a consented, offline sign-in.
                "access_type": "offline",
                "prompt": "consent select_account",
                "include_granted_scopes": "true",
            }
        )
        expires_at = time.time() + _PENDING_TTL
        self.store.save("pending", {"state": state, "verifier": verifier, "url": url, "expires_at": expires_at})
        # Lets the callback endpoint tell a link it issued from a forged or expired one.
        self.storage.set(signin_key(state), json.dumps({"expires_at": expires_at}).encode())
        return (
            "The user has not signed in to Google yet. Give them this link to sign in with their own "
            "Google account (valid for 15 minutes), and call this tool again after they say they are done:\n"
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
            payload = self._token_request({"grant_type": "refresh_token", "refresh_token": token["refresh_token"]})
        except UserAuthError as e:
            if e.status not in (400, 401):
                raise
            # invalid_grant: revoked, password changed, unused for 6 months, or 7 days old on a "Testing" app.
            self.store.delete("token")
            raise SignInRequired(self._start_sign_in()) from e
        return self._store_token(payload, token["refresh_token"], token.get("account"))["access_token"]

    def _store_token(
        self, payload: Mapping[str, Any], previous_refresh_token: str | None = None, account: str | None = None
    ) -> dict[str, Any]:
        if not payload.get("access_token"):
            raise UserAuthError("Google returned no access token.")
        token = {
            "access_token": payload["access_token"],
            # Google returns a refresh token on the first exchange only; refreshes keep the old one.
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
            response = requests.post(TOKEN_URL, data=data, timeout=30)
        except requests.exceptions.RequestException as e:
            raise UserAuthError(f"Could not reach Google: {e}") from e
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code != 200:
            detail = payload.get("error_description") or payload.get("error") or response.text[:300]
            raise UserAuthError(f"Google sign-in failed ({response.status_code}): {detail}", response.status_code)
        return payload
