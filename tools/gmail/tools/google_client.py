"""
Shared Google plumbing: which credential mode is in use, and how requests are sent.

The plugin accepts two kinds of credentials:

- OAuth: a Google sign-in from the Dify console; the token acts as that one account for
  everybody using the workspace credential.
- Each user signs in: the OAuth client (client ID + secret), the sign-in callback URL and
  ``auth_mode: per_user``; every Dify user gets their own Google token (see ``user_auth``).

Every ID that goes into a URL path is encoded here, so a value chosen by the model cannot
change the request path.
"""

from dataclasses import dataclass, field
from typing import Any, Generator, Mapping
from urllib.parse import quote

import requests

from tools.user_auth import PRODUCT, SignInRequired, UserAuthError, UserSignIn


class GoogleAuthError(Exception):
    """A Google call that could not be made or did not succeed; the message is shown to the user."""


def is_per_user(credentials: Mapping[str, Any]) -> bool:
    if credentials.get("access_token"):
        return False
    if credentials.get("auth_mode") == "per_user":
        return True
    # The per-user fields filled in without choosing the mode.
    return bool(credentials.get("client_id")) and bool(credentials.get("redirect_uri"))


@dataclass
class GoogleContext:
    access_token: str = field(repr=False)
    # Set for per-user sign-in, so a token Google rejects can be replaced by a new sign-in.
    sign_in: UserSignIn | None = field(default=None, repr=False)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"}


def resolve_context(credentials: Mapping[str, Any], tool: Any = None) -> GoogleContext:
    """
    The token to use. ``tool`` is the calling Tool; per-user sign-in needs its user ID and plugin
    storage. When that user has not signed in yet, the GoogleAuthError message is the sign-in link.
    """
    if is_per_user(credentials):
        if tool is None:
            raise GoogleAuthError("Per-user sign-in is not available here.")
        sign_in = user_sign_in(credentials, tool)
        try:
            token = sign_in.access_token()
        except (SignInRequired, UserAuthError) as e:
            raise GoogleAuthError(str(e)) from e
        if sign_in.just_signed_in:
            # @with_outputs (or connect()) tells the user which account they signed in with.
            tool._signed_in_as = sign_in.just_signed_in
        return GoogleContext(token, sign_in)
    token = credentials.get("access_token")
    if not token:
        raise GoogleAuthError(f"{PRODUCT} access token is required. Please configure OAuth authentication.")
    return GoogleContext(token)


def user_sign_in(credentials: Mapping[str, Any], tool: Any) -> UserSignIn:
    try:
        return UserSignIn(credentials, tool.runtime.user_id, tool.session.storage)
    except UserAuthError as e:
        raise GoogleAuthError(str(e)) from e


def connect(tool: Any) -> Generator[Any, None, str | None]:
    """
    ``access_token = yield from connect(self)`` in the original tools: the token for the tool's
    credential, or None after yielding the reason (for per-user sign-in, the link to open).
    """
    try:
        ctx = resolve_context(tool.runtime.credentials, tool)
    except GoogleAuthError as e:
        yield tool.create_text_message(str(e))
        return None
    if getattr(tool, "_signed_in_as", None):
        yield tool.create_text_message(
            f"(Signed in to Google as {tool._signed_in_as}. If this is not the user's account, "
            "they can ask to sign out and sign in again.)"
        )
    return ctx.access_token


def segment(value: Any) -> str:
    """Quote an ID for use as one URL path segment."""
    return quote(str(value).strip(), safe="")


def google_request(
    ctx: GoogleContext,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
    timeout: int = 30,
) -> requests.Response:
    """Call a Google API URL; network errors and non-2xx answers raise GoogleAuthError."""
    extra: dict[str, Any] = {"json": json_body} if json_body is not None else {}
    try:
        response = requests.request(
            method, url, headers=ctx.headers, params={k: v for k, v in (params or {}).items() if v is not None},
            timeout=timeout, **extra,
        )
    except requests.exceptions.RequestException as e:
        raise GoogleAuthError(f"Network error: {e}") from e
    if response.status_code == 401 and ctx.sign_in is not None:
        # The user's token was revoked: hand them a new sign-in link.
        raise GoogleAuthError(ctx.sign_in.expired())
    if response.status_code < 200 or response.status_code >= 300:
        raise GoogleAuthError(describe_error(response))
    return response


def json_of(response: requests.Response) -> Any:
    if response.status_code == 204 or not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def describe_error(response: requests.Response) -> str:
    try:
        error = response.json().get("error") or {}
        detail = error.get("message", "") if isinstance(error, Mapping) else str(error)
    except (ValueError, AttributeError):
        detail = response.text[:300]
    hint = {
        401: "The sign-in has expired or the token is invalid; re-authorize the plugin.",
        403: f"Permission denied: the account may not do this, or the {PRODUCT} API is not enabled for the OAuth client's project.",
        404: "Not found, or the account cannot see it: check the ID.",
        429: "Google is rate-limiting requests; wait a moment and retry.",
    }.get(response.status_code, "")
    return f"{PRODUCT} API error {response.status_code}" + (f": {detail}" if detail else "") + (f" {hint}" if hint else "")


def require(tool_parameters: Mapping[str, Any], *names: str) -> list[str]:
    values = []
    for name in names:
        value = str(tool_parameters.get(name) or "").strip()
        if not value:
            raise GoogleAuthError(f"{name} is required.")
        values.append(value)
    return values
