"""
Shared Confluence plumbing: which credential mode is in use, where to send requests, and how.

The plugin accepts three kinds of credentials:

- API token (the original mode): Confluence URL + username (email) + API token. Cloud sites
  (*.atlassian.net) use the v2 API; Server / Data Center the v1 REST API. Without a username
  the token is sent as a Bearer personal access token (Server / Data Center).
- OAuth: an Atlassian OAuth 2.0 (3LO) sign-in from the Dify console; the token acts as that
  one account for everybody using the workspace credential.
- Each user signs in: the OAuth app fields plus ``auth_mode: per_user``; every Dify user
  gets their own Atlassian token (see ``user_auth``).

OAuth tokens are only sent to ``https://api.atlassian.com/ex/confluence/<cloud id>``. Every ID
that goes into a URL path is encoded here, so a value chosen by the model cannot change the
request path.
"""

import base64
import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Mapping
from urllib.parse import parse_qsl, quote, urlparse

import requests
from atlassian import ConfluenceV2
from atlassian.confluence import ConfluenceServer

from tools import atlassian
from tools.user_auth import SignInRequired, UserAuthError, UserSignIn


class ConfluenceAuthError(Exception):
    """A Confluence call that could not be made or did not succeed; the message is shown to the user."""


def is_per_user(credentials: Mapping[str, Any]) -> bool:
    if credentials.get("access_token"):
        return False
    if credentials.get("auth_mode") == "per_user":
        return True
    # The OAuth app fields filled in without a token: the Mode select (default "API token") was left
    # unchanged by mistake, since nothing else can use these fields.
    return not credentials.get("token") and bool(credentials.get("client_id")) and bool(credentials.get("redirect_uri"))


def is_oauth(credentials: Mapping[str, Any]) -> bool:
    return bool(credentials.get("access_token"))


def is_cloud_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host.endswith((".atlassian.net", ".jira.com"))


@dataclass(frozen=True)
class ConfluenceContext:
    # The site root (Cloud: without /wiki), or https://api.atlassian.com/ex/confluence/<cloud id> for OAuth.
    base_url: str
    headers: dict[str, str] = field(hash=False)
    cloud: bool
    # The site's own URL, for links people can open ("" when unknown).
    site_url: str = ""
    # The raw token for atlassian-python-api: ("bearer", token) or ("basic", (user, token)).
    auth: tuple = field(default=(), hash=False, repr=False)

    def v2(self, path: str) -> str:
        """Cloud v2 API."""
        return f"{self.base_url}/wiki/api/v2/{path}"

    def v1(self, path: str) -> str:
        """v1 REST API: under /wiki on Cloud, at the context root on Server / Data Center."""
        return f"{self.base_url}/wiki/rest/api/{path}" if self.cloud else f"{self.base_url}/rest/api/{path}"

    def web(self, webui: str) -> str:
        """A link people can open, from a ``_links.webui`` path."""
        if not webui or not self.site_url:
            return ""
        return f"{self.site_url}/wiki{webui}" if self.cloud else f"{self.site_url}{webui}"


def resolve_context(credentials: Mapping[str, Any], tool: Any = None) -> ConfluenceContext:
    """
    Turn the runtime credentials into a Confluence context. ``tool`` is the calling Tool; per-user
    sign-in needs its user ID and plugin storage. When that user has not signed in yet, the
    ConfluenceAuthError message is the sign-in link.
    """
    if is_per_user(credentials):
        if tool is None:
            raise ConfluenceAuthError("Per-user sign-in is not available here.")
        token = user_token(credentials, tool)
        return _oauth_context(token["access_token"], token["cloud_id"], token.get("site_url", ""))
    if is_oauth(credentials):
        if not credentials.get("cloud_id"):
            raise ConfluenceAuthError("This authorization has no Confluence site; authorize the plugin again.")
        return _oauth_context(credentials["access_token"], credentials["cloud_id"], credentials.get("site_url", ""))

    url = (credentials.get("url") or "").strip().rstrip("/")
    token = (credentials.get("token") or "").strip()
    if not url or not token:
        raise ConfluenceAuthError(
            "Confluence URL and Access Token are required. (For Atlassian sign-in per user, set Mode to "
            "'Each user signs in'.)"
        )
    cloud = is_cloud_url(url)
    if cloud and url.endswith("/wiki"):
        url = url[: -len("/wiki")]
    username = (credentials.get("username") or "").strip()
    if username:
        basic = base64.b64encode(f"{username}:{token}".encode()).decode()
        headers = {"Accept": "application/json", "Authorization": f"Basic {basic}"}
        auth = ("basic", (username, token))
    else:
        headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
        auth = ("bearer", token)
    return ConfluenceContext(url, headers, cloud, url, auth)


def _oauth_context(access_token: str, cloud_id: str, site_url: str) -> ConfluenceContext:
    return ConfluenceContext(
        f"{atlassian.API_HOST}/ex/confluence/{quote(str(cloud_id), safe='')}",
        {"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        True,
        site_url.rstrip("/"),
        ("bearer", access_token),
    )


def user_sign_in(credentials: Mapping[str, Any], tool: Any) -> UserSignIn:
    try:
        return UserSignIn(credentials, tool.runtime.user_id, tool.session.storage)
    except UserAuthError as e:
        raise ConfluenceAuthError(str(e)) from e


def user_token(credentials: Mapping[str, Any], tool: Any) -> dict[str, Any]:
    sign_in = user_sign_in(credentials, tool)
    try:
        token = sign_in.token()
    except (SignInRequired, UserAuthError) as e:
        raise ConfluenceAuthError(str(e)) from e
    if sign_in.just_signed_in:
        # @with_outputs tells the user which account they signed in with.
        tool._signed_in_as = sign_in.just_signed_in
    return token


def auth(credentials: Mapping[str, Any], tool: Any = None) -> ConfluenceV2 | ConfluenceServer:
    """An atlassian-python-api client for any credential mode (used by the original tools)."""
    ctx = resolve_context(credentials, tool)
    client = ConfluenceV2 if ctx.cloud else ConfluenceServer
    # The library adds /wiki to *.atlassian.net URLs itself, but not to API-gateway URLs
    # (api.atlassian.com/ex/confluence/<cloud id>), where it must be part of the base.
    url = f"{ctx.base_url}/wiki" if ctx.base_url.startswith(atlassian.API_HOST) else ctx.base_url
    kind, secret = ctx.auth
    if kind == "bearer":
        return client(url=url, token=secret, cloud=ctx.cloud)
    return client(url=url, username=secret[0], password=secret[1], cloud=ctx.cloud)


def segment(value: Any) -> str:
    """Quote an ID for use as one URL path segment."""
    return quote(str(value).strip(), safe="")


def confluence_request(
    ctx: ConfluenceContext,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
    files: Any = None,
    headers: Mapping[str, str] | None = None,
    timeout: int = 30,
) -> requests.Response:
    """Call a Confluence URL with the context's auth; network errors and non-2xx answers raise ConfluenceAuthError."""
    extra: dict[str, Any] = {}
    if json_body is not None:
        extra["json"] = json_body
    if files is not None:
        extra["files"] = files
    try:
        response = requests.request(
            method, url, headers={**ctx.headers, **(headers or {})}, params=params, timeout=timeout, **extra
        )
    except requests.exceptions.RequestException as e:
        raise ConfluenceAuthError(f"Network error: {e}") from e
    if response.status_code < 200 or response.status_code >= 300:
        raise ConfluenceAuthError(describe_error(response))
    return response


def json_or_empty(response: requests.Response) -> Any:
    if response.status_code == 204 or not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def describe_error(response: requests.Response) -> str:
    detail = ""
    try:
        body = response.json()
        if isinstance(body, Mapping):
            errors = body.get("errors")
            if isinstance(errors, list) and errors:
                detail = "; ".join(str(e.get("title") or e.get("detail") or e) for e in errors if e)
            detail = detail or str(body.get("message") or "")
    except ValueError:
        detail = response.text[:300]
    hint = {
        401: "The sign-in has expired or the token is invalid; re-authorize the plugin.",
        403: "Permission denied: the account (or the OAuth app's scopes) may not do this.",
        404: "Not found, or the account cannot see it: check the page, space, comment or attachment ID.",
        409: "Conflict: the page was changed by someone else, or a page with this title already exists in the space.",
        429: "Confluence is rate-limiting requests; wait a moment and retry.",
    }.get(response.status_code, "")
    return f"Confluence API error {response.status_code}" + (f": {detail}" if detail else "") + (f" {hint}" if hint else "")


def require(tool_parameters: Mapping[str, Any], *names: str) -> list[str]:
    values = []
    for name in names:
        value = str(tool_parameters.get(name) or "").strip()
        if not value:
            raise ConfluenceAuthError(f"{name} is required.")
        values.append(value)
    return values


def clamp(value: Any, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(number, maximum))


def next_cursor(body: Mapping[str, Any]) -> str | None:
    """The cursor of the next page of a v2 listing (from _links.next), if any."""
    link = ((body.get("_links") or {}).get("next")) or ""
    # Decoded: the link's cursor is URL-encoded, and requests encodes parameters again.
    return dict(parse_qsl(urlparse(link).query)).get("cursor")


# ── page bodies ───────────────────────────────────────────────────────


def to_storage(text: str, body_format: str | None) -> str:
    """Page or comment content in Confluence storage format, from Markdown (default) or storage XHTML."""
    if (body_format or "markdown").lower() == "storage":
        return text
    import markdown

    return markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"], output_format="xhtml")


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in ("td", "th"):
            self.parts.append(" | ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        # List items end where the next one starts, so they stay on consecutive lines.
        if tag in self.BLOCK and tag != "li":
            self.parts.append("\n")

    def handle_data(self, data):
        # Whitespace between tags (e.g. the newline between two <li>) is layout, not text.
        if data.strip() or "\n" not in data:
            self.parts.append(data)


def storage_to_text(storage: str | None) -> str:
    """Readable plain text of storage-format XHTML, for the model and for workflows."""
    if not storage:
        return ""
    parser = _TextExtractor()
    parser.feed(storage)
    text = html.unescape("".join(parser.parts))
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ── Confluence objects ────────────────────────────────────────────────


def page_dict(ctx: ConfluenceContext, page: Mapping[str, Any], with_body: bool = False) -> dict[str, Any]:
    """A page from the v2 API (Cloud) or the v1 content API (Server)."""
    version = page.get("version") or {}
    storage = ((page.get("body") or {}).get("storage") or {}).get("value", "")
    space = page.get("space") or {}
    result = {
        "id": str(page.get("id", "")),
        "title": page.get("title", ""),
        "status": page.get("status", ""),
        "space_id": str(page.get("spaceId") or space.get("id") or ""),
        "space_key": space.get("key", ""),
        "parent_id": str(page.get("parentId") or ""),
        "version": int(version.get("number") or 0),
        "updated": version.get("createdAt") or version.get("when") or "",
        "url": ctx.web((page.get("_links") or {}).get("webui", "")),
    }
    if with_body:
        result["body_storage"] = storage
        result["body_text"] = storage_to_text(storage)
    return result


def comment_dict(comment: Mapping[str, Any]) -> dict[str, Any]:
    storage = ((comment.get("body") or {}).get("storage") or {}).get("value", "")
    version = comment.get("version") or {}
    return {
        "id": str(comment.get("id", "")),
        "body": storage_to_text(storage),
        "author_id": version.get("authorId") or ((version.get("by") or {}).get("accountId")) or "",
        "created": version.get("createdAt") or version.get("when") or "",
    }


def attachment_dict(attachment: Mapping[str, Any]) -> dict[str, Any]:
    extensions = attachment.get("extensions") or {}
    return {
        "id": str(attachment.get("id", "")),
        "title": attachment.get("title", ""),
        "media_type": attachment.get("mediaType") or extensions.get("mediaType") or "",
        "size": int(attachment.get("fileSize") or extensions.get("fileSize") or 0),
        "page_id": str(attachment.get("pageId") or ((attachment.get("container") or {}).get("id")) or ""),
    }
