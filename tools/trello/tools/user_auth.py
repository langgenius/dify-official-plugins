"""
"Each user signs in" mode: every chat user acts with their own Trello account.

Trello has no authorization-code flow: its authorize page hands the token to the browser in
the URL fragment (``#token=...``). The sign-in works like this:

1. the tool finds no token for ``runtime.user_id``. It saves a pending sign-in: a random state
   and a one-time RSA key pair, whose private key stays in the user's encrypted record and whose
   public key goes with the state. It returns the Trello authorize link as its result;
2. Trello sends the browser to the callback endpoint with the token in the fragment. The page's
   script posts it back to the endpoint, which seals it with the state's public key and stores
   only that ciphertext; the endpoint cannot read it back;
3. on the user's next request the tool opens the sealed token with the private key, checks it
   against Trello (``/members/me``) and keeps it in plugin storage.

Everything stored per user is encrypted with a key derived from the API secret, so plugin
storage alone does not reveal a token, and rotating the secret signs everybody out. Tokens
never appear in tool output or in URLs.
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
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

AUTHORIZE_URL = "https://trello.com/1/authorize"
API = "https://api.trello.com/1"
EXPIRATIONS = ("1day", "30days", "never")

# A sign-in link stays usable this long.
_PENDING_TTL = 15 * 60

# Storage keys: per-user state under user/<hash>, callback data under signin/<state>.
_STATE_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
_OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


class SignInRequired(Exception):
    """The current user has to (finish) signing in; the message carries the link for them."""


class UserAuthError(Exception):
    """Per-user sign-in is misconfigured or Trello rejected it."""


def is_valid_state(state: str) -> bool:
    return 20 <= len(state) <= 64 and set(state) <= _STATE_CHARS


def signin_key(state: str) -> str:
    return f"signin/{state}"


def code_key(state: str) -> str:
    return f"signin/{state}.code"


def seal(public_key_pem: str, token: str) -> str:
    """Encrypt a token with a sign-in's public key (used by the callback endpoint)."""
    key = serialization.load_pem_public_key(public_key_pem.encode())
    return base64.b64encode(key.encrypt(token.encode(), _OAEP)).decode()


def auth_header(api_key: str, token: str) -> dict[str, str]:
    """Trello accepts the key and token in this header, which keeps them out of URLs."""
    return {"Authorization": f'OAuth oauth_consumer_key="{api_key}", oauth_token="{token}"'}


def _user_key(credentials: Mapping[str, Any], user_id: str, name: str) -> str:
    # Scoped to the API key so switching keys never reuses another key's tokens.
    digest = hashlib.sha256(f"{credentials.get('trello_api_key', '')}|{user_id}".encode()).hexdigest()
    return f"user/{digest}/{name}"


def _fernet(credentials: Mapping[str, Any]) -> Fernet:
    secret = (credentials.get("trello_api_secret") or "").encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"dify-trello-per-user-token").derive(secret)
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
            # Written with another API secret: treat as signed out.
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
    """Get a Trello token for one chat user, starting a sign-in when there is none."""

    def __init__(self, credentials: Mapping[str, Any], user_id: str | None, storage: Any):
        if not user_id:
            raise UserAuthError("This credential uses per-user sign-in, but Dify did not say which user is calling the tool.")
        self.credentials = credentials
        self.storage = storage
        self.store = UserTokenStore(storage, credentials, user_id)
        self.api_key = (credentials.get("trello_api_key") or "").strip()
        self.redirect_uri = (credentials.get("redirect_uri") or "").strip()
        self.expiration = credentials.get("token_expiration") or "30days"
        # Set when this call finished a sign-in: the account the user signed in with.
        self.just_signed_in: str | None = None
        if not self.redirect_uri:
            raise UserAuthError(
                "Per-user sign-in needs the Sign-in Callback URL: create the plugin's 'Trello sign-in' "
                "endpoint and paste its URL into the credential."
            )

    def token(self) -> str:
        record = self.store.load("token")
        if record is None:
            record = self._finish_pending_sign_in()
        return record["token"]

    def account(self) -> str | None:
        record = self.store.load("token")
        return record.get("account") if record else None

    def sign_out(self) -> bool:
        had_token = self.store.load("token") is not None
        pending = self.store.load("pending")
        if pending:
            self._forget_state(pending["state"])
        self.store.delete("token")
        self.store.delete("pending")
        return had_token

    def expired(self) -> str:
        """Trello rejected the stored token (revoked or expired): forget it and start a new sign-in."""
        self.store.delete("token")
        return self._start_sign_in(
            "The user's Trello sign-in has expired or was revoked. Give them this link to sign in again "
            "(valid for 15 minutes), and call this tool again after they say they are done:\n"
        )

    # ── sign-in ───────────────────────────────────────────────────────

    def _finish_pending_sign_in(self) -> dict[str, Any]:
        pending = self.store.load("pending")
        if pending is None or pending["expires_at"] < time.time():
            if pending:
                self._forget_state(pending["state"])
            raise SignInRequired(self._start_sign_in())

        callback = self._take_callback(pending["state"])
        if callback is None:
            raise SignInRequired(
                "Sign-in has not been completed yet. Ask the user to open this link, sign in to Trello and "
                f"click Allow, then tell you when they are done:\n{pending['url']}"
            )
        self.store.delete("pending")
        self._forget_state(pending["state"])
        if callback.get("error"):
            raise UserAuthError(f"Trello sign-in failed: {callback['error']}. Ask the user to try again.")
        try:
            private_key = serialization.load_pem_private_key(pending["private_key"].encode(), password=None)
            token = private_key.decrypt(base64.b64decode(callback["sealed"]), _OAEP).decode()
        except (KeyError, ValueError) as e:
            raise UserAuthError("The Trello sign-in response could not be read. Ask the user to try again.") from e

        account, member_id = self._check(token)
        self.just_signed_in = account
        record = {"token": token, "account": account, "member_id": member_id, "signed_in_at": time.time()}
        self.store.save("token", record)
        return record

    def _check(self, token: str) -> tuple[str, str]:
        """Who the token belongs to; also proves it works with this API key."""
        try:
            response = requests.get(
                f"{API}/members/me", headers=auth_header(self.api_key, token),
                params={"fields": "username,fullName"}, timeout=15,
            )
        except requests.exceptions.RequestException as e:
            raise UserAuthError(f"Could not reach Trello: {e}") from e
        if response.status_code != 200:
            raise UserAuthError(f"Trello did not accept the new sign-in ({response.status_code}). Ask the user to try again.")
        me = response.json()
        name = me.get("fullName") or ""
        username = me.get("username") or ""
        return (f"{name} (@{username})" if name and username else name or username or "an unknown account"), me.get("id", "")

    def _start_sign_in(self, intro: str | None = None) -> str:
        state = secrets.token_urlsafe(32)
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        return_url = f"{self.redirect_uri}{'&' if '?' in self.redirect_uri else '?'}state={state}"
        url = f"{AUTHORIZE_URL}?" + urllib.parse.urlencode(
            {
                "key": self.api_key,
                "name": (self.credentials.get("app_name") or "Dify").strip() or "Dify",
                "scope": "read,write",
                "expiration": self.expiration if self.expiration in EXPIRATIONS else "30days",
                "response_type": "token",
                "callback_method": "fragment",
                "return_url": return_url,
            }
        )
        expires_at = time.time() + _PENDING_TTL
        self.store.save("pending", {"state": state, "private_key": private_pem, "url": url, "expires_at": expires_at})
        # Lets the callback endpoint tell a link it issued from a forged or expired one, and seal the token.
        self.storage.set(signin_key(state), json.dumps({"expires_at": expires_at, "public_key": public_pem}).encode())
        return (intro or (
            "The user has not signed in to Trello yet. Give them this link to sign in with their own Trello "
            "account and click Allow (valid for 15 minutes), and call this tool again after they say they are done:\n"
        )) + url

    def _take_callback(self, state: str) -> dict[str, Any] | None:
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
