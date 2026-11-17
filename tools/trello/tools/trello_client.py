"""
Shared Trello plumbing: which credential mode is in use, and how requests are sent.

The plugin accepts two kinds of credentials:

- API key + token (the original mode): everybody uses the token's Trello account.
- Each user signs in: the API key + secret, the sign-in callback URL and ``auth_mode: per_user``;
  every Dify user gets their own Trello token (see ``user_auth``).

The key and token always travel in the Authorization header, never in the URL, and every ID
that goes into a path is encoded, so a value chosen by the model cannot change the request path.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import quote

import requests

from tools.user_auth import API, SignInRequired, UserAuthError, UserSignIn, auth_header


class TrelloAuthError(Exception):
    """A Trello call that could not be made or did not succeed; the message is shown to the user."""


def is_per_user(credentials: Mapping[str, Any]) -> bool:
    if credentials.get("auth_mode") == "per_user":
        return True
    # The per-user fields filled in without a token: the Mode select was left on its default by mistake.
    return not credentials.get("trello_api_token") and bool(credentials.get("redirect_uri"))


@dataclass
class TrelloContext:
    api_key: str
    token: str = field(repr=False)
    # Set for per-user sign-in, so a token Trello rejects can be replaced by a new sign-in.
    sign_in: UserSignIn | None = field(default=None, repr=False)

    @property
    def headers(self) -> dict[str, str]:
        return {"Accept": "application/json", **auth_header(self.api_key, self.token)}


def resolve_context(credentials: Mapping[str, Any], tool: Any = None) -> TrelloContext:
    """
    The API key and the token to use. ``tool`` is the calling Tool; per-user sign-in needs its user ID
    and plugin storage. When that user has not signed in yet, the TrelloAuthError message is the link.
    """
    api_key = (credentials.get("trello_api_key") or "").strip()
    if not api_key:
        raise TrelloAuthError("The Trello API key is missing from the credential.")
    if is_per_user(credentials):
        if tool is None:
            raise TrelloAuthError("Per-user sign-in is not available here.")
        sign_in = user_sign_in(credentials, tool)
        try:
            token = sign_in.token()
        except (SignInRequired, UserAuthError) as e:
            raise TrelloAuthError(str(e)) from e
        if sign_in.just_signed_in:
            # @with_outputs tells the user which account they signed in with.
            tool._signed_in_as = sign_in.just_signed_in
        return TrelloContext(api_key, token, sign_in)
    token = (credentials.get("trello_api_token") or "").strip()
    if not token:
        raise TrelloAuthError(
            "The Trello API token is missing. (For Trello sign-in per user, set Mode to 'Each user signs in'.)"
        )
    return TrelloContext(api_key, token)


def user_sign_in(credentials: Mapping[str, Any], tool: Any) -> UserSignIn:
    try:
        return UserSignIn(credentials, tool.runtime.user_id, tool.session.storage)
    except UserAuthError as e:
        raise TrelloAuthError(str(e)) from e


def credentials_of(tool: Any) -> tuple[str, str]:
    """(API key, token) for the original tools, which build their own requests."""
    ctx = resolve_context(tool.runtime.credentials, tool)
    tool._trello_ctx = ctx
    return ctx.api_key, ctx.token


def segment(value: Any) -> str:
    """Quote an ID for use as one URL path segment."""
    return quote(str(value).strip(), safe="")


def trello_request(
    ctx: TrelloContext,
    method: str,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
    files: Any = None,
    data: Any = None,
    headers: Mapping[str, str] | None = None,
    timeout: int = 30,
) -> requests.Response:
    """Call ``https://api.trello.com/1/<path>``; network errors and non-2xx answers raise TrelloAuthError."""
    extra: dict[str, Any] = {}
    if json_body is not None:
        extra["json"] = json_body
    if files is not None:
        extra["files"] = files
    if data is not None:
        extra["data"] = data
    url = path if path.startswith(API + "/") else f"{API}/{path.lstrip('/')}"
    try:
        response = requests.request(
            method, url, headers={**ctx.headers, **(headers or {})},
            params={k: v for k, v in (params or {}).items() if v is not None}, timeout=timeout, **extra,
        )
    except requests.exceptions.RequestException as e:
        raise TrelloAuthError(f"Network error: {e}") from e
    if response.status_code == 401 and ctx.sign_in is not None:
        # The user's token expired or was revoked: hand them a new sign-in link.
        raise TrelloAuthError(ctx.sign_in.expired())
    if response.status_code < 200 or response.status_code >= 300:
        raise TrelloAuthError(describe_error(response))
    return response


def json_of(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {}


def describe_error(response: requests.Response) -> str:
    try:
        body = response.json()
        detail = body.get("message") or body.get("error") or "" if isinstance(body, Mapping) else str(body)
    except ValueError:
        detail = response.text[:300].strip()
    hint = {
        401: "The Trello key or token is invalid, expired or was revoked.",
        403: "Permission denied: the account may not change this board, card or list.",
        404: "Not found, or the account cannot see it: check the ID (get IDs from the list and search tools).",
        429: "Trello is rate-limiting requests; wait a moment and retry.",
    }.get(response.status_code, "")
    return f"Trello API error {response.status_code}" + (f": {detail}" if detail else "") + (f" {hint}" if hint else "")


def require(tool_parameters: Mapping[str, Any], *names: str) -> list[str]:
    values = []
    for name in names:
        value = str(tool_parameters.get(name) or "").strip()
        if not value:
            raise TrelloAuthError(f"{name} is required.")
        values.append(value)
    return values


def split_ids(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


# ── Trello objects ────────────────────────────────────────────────────


def card_dict(card: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": card.get("id", ""),
        "name": card.get("name", ""),
        "desc": card.get("desc", ""),
        "list_id": card.get("idList", ""),
        "board_id": card.get("idBoard", ""),
        "due": card.get("due") or "",
        "due_complete": bool(card.get("dueComplete")),
        "closed": bool(card.get("closed")),
        "labels": [label.get("name") or label.get("color") or "" for label in card.get("labels") or []],
        "member_ids": list(card.get("idMembers") or []),
        "url": card.get("shortUrl") or card.get("url") or "",
    }


def checklist_dict(checklist: Mapping[str, Any]) -> dict[str, Any]:
    items = [
        {"id": i.get("id", ""), "name": i.get("name", ""), "state": i.get("state", ""), "complete": i.get("state") == "complete"}
        for i in sorted(checklist.get("checkItems") or [], key=lambda i: i.get("pos") or 0)
    ]
    return {
        "id": checklist.get("id", ""),
        "name": checklist.get("name", ""),
        "card_id": checklist.get("idCard", ""),
        "items": items,
        "completed": sum(1 for i in items if i["complete"]),
        "total": len(items),
    }


def label_dict(label: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": label.get("id", ""), "name": label.get("name", ""), "color": label.get("color") or ""}


def member_dict(member: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": member.get("id", ""), "username": member.get("username", ""), "full_name": member.get("fullName", "")}


def attachment_dict(attachment: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": attachment.get("id", ""),
        "name": attachment.get("name", ""),
        "mime_type": attachment.get("mimeType") or "",
        "size": int(attachment.get("bytes") or 0),
        "is_upload": bool(attachment.get("isUpload")),
        "url": attachment.get("url", ""),
        "date": attachment.get("date", ""),
    }
