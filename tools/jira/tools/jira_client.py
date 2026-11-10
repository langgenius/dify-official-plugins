"""
Shared Jira plumbing: which credential mode is in use, where to send requests, and how.

The plugin accepts three kinds of credentials:

- API token (the original mode): Jira URL + "Basic" (Cloud, base64 of email:API token)
  or "Bearer" (Server / Data Center personal access token).
- OAuth: an Atlassian OAuth 2.0 (3LO) sign-in from the Dify console; the token acts as
  that one account for everybody using the workspace credential.
- Each user signs in: the OAuth app fields plus ``auth_mode: per_user``; every Dify user
  gets their own Atlassian token (see ``user_auth``).

OAuth tokens are not sent to the site URL: Atlassian only accepts them at
``https://api.atlassian.com/ex/jira/<cloud id>``. Every ID or key that goes into a URL path
is encoded here, so a value chosen by the model cannot change the request path.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import quote

import requests
from atlassian.jira import Jira

from tools import atlassian
from tools.user_auth import SignInRequired, UserAuthError, UserSignIn


class JiraAuthError(Exception):
    """A Jira call that could not be made or did not succeed; the message is shown to the user."""


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


@dataclass(frozen=True)
class JiraContext:
    # Where /rest/... lives: the site itself, or https://api.atlassian.com/ex/jira/<cloud id> for OAuth.
    base_url: str
    headers: dict[str, str] = field(hash=False)
    cloud: bool
    # The site's own URL, for links people can open ("" when unknown).
    site_url: str = ""

    @property
    def api_version(self) -> str:
        # Cloud speaks v3 (descriptions and comments in Atlassian Document Format); Server only v2.
        return "3" if self.cloud else "2"

    def api(self, path: str) -> str:
        return f"{self.base_url}/rest/api/{self.api_version}/{path}"

    def agile(self, path: str) -> str:
        return f"{self.base_url}/rest/agile/1.0/{path}"

    def browse(self, key: str) -> str:
        return f"{self.site_url}/browse/{quote(key)}" if self.site_url and key else ""


def resolve_context(credentials: Mapping[str, Any], tool: Any = None) -> JiraContext:
    """
    Turn the runtime credentials into a Jira context. ``tool`` is the calling Tool; per-user
    sign-in needs its user ID and plugin storage. When that user has not signed in yet, the
    JiraAuthError message is the sign-in link.
    """
    accept = {"Accept": "application/json"}
    if is_per_user(credentials):
        if tool is None:
            raise JiraAuthError("Per-user sign-in is not available here.")
        token = user_token(credentials, tool)
        return _oauth_context(token["access_token"], token["cloud_id"], token.get("site_url", ""))
    if is_oauth(credentials):
        if not credentials.get("cloud_id"):
            raise JiraAuthError("This authorization has no Jira site; authorize the plugin again.")
        return _oauth_context(credentials["access_token"], credentials["cloud_id"], credentials.get("site_url", ""))

    url = (credentials.get("url") or "").strip().rstrip("/")
    token = (credentials.get("token") or "").strip()
    if not url or not token:
        raise JiraAuthError(
            "Jira URL and Access Token are required. (For Atlassian sign-in per user, set Mode to 'Each user signs in'.)"
        )
    token_type = credentials.get("token_type") or "Bearer"
    return JiraContext(url, {**accept, "Authorization": f"{token_type} {token}"}, token_type == "Basic", url)


def _oauth_context(access_token: str, cloud_id: str, site_url: str) -> JiraContext:
    return JiraContext(
        f"{atlassian.API_HOST}/ex/jira/{quote(str(cloud_id), safe='')}",
        {"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        True,
        site_url,
    )


def user_sign_in(credentials: Mapping[str, Any], tool: Any) -> UserSignIn:
    try:
        return UserSignIn(credentials, tool.runtime.user_id, tool.session.storage)
    except UserAuthError as e:
        raise JiraAuthError(str(e)) from e


def user_token(credentials: Mapping[str, Any], tool: Any) -> dict[str, Any]:
    sign_in = user_sign_in(credentials, tool)
    try:
        token = sign_in.token()
    except (SignInRequired, UserAuthError) as e:
        raise JiraAuthError(str(e)) from e
    if sign_in.just_signed_in:
        # @with_outputs tells the user which account they signed in with.
        tool._signed_in_as = sign_in.just_signed_in
    return token


def auth(credentials: Mapping[str, Any], tool: Any = None) -> Jira:
    """An atlassian-python-api client for any credential mode (used by the original tools)."""
    ctx = resolve_context(credentials, tool)
    return Jira(
        url=ctx.base_url,
        header={"Content-Type": "application/json", **ctx.headers},
        cloud=ctx.cloud,
        api_version=ctx.api_version,
    )


def segment(value: Any) -> str:
    """Quote an ID or key for use as one URL path segment."""
    return quote(str(value).strip(), safe="")


def jira_request(
    ctx: JiraContext,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
    files: Any = None,
    headers: Mapping[str, str] | None = None,
    timeout: int = 30,
) -> requests.Response:
    """Call a Jira URL with the context's auth; network errors and non-2xx answers raise JiraAuthError."""
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
        raise JiraAuthError(f"Network error: {e}") from e
    if response.status_code < 200 or response.status_code >= 300:
        raise JiraAuthError(describe_error(response))
    return response


def json_or_empty(response: requests.Response) -> Any:
    if response.status_code == 204 or not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def describe_error(response: requests.Response) -> str:
    try:
        body = response.json()
        messages = list(body.get("errorMessages") or [])
        messages += [f"{k}: {v}" for k, v in (body.get("errors") or {}).items()]
        detail = "; ".join(messages) or body.get("message") or ""
    except (ValueError, AttributeError):
        detail = response.text[:300]
    hint = {
        401: "The sign-in has expired or the token is invalid; re-authorize the plugin.",
        403: "Permission denied: the account (or the OAuth app's scopes) may not do this.",
        404: "Not found, or the account cannot see it: check the issue key, project key or ID.",
        429: "Jira is rate-limiting requests; wait a moment and retry.",
    }.get(response.status_code, "")
    return f"Jira API error {response.status_code}" + (f": {detail}" if detail else "") + (f" {hint}" if hint else "")


def require(tool_parameters: Mapping[str, Any], *names: str) -> list[str]:
    values = []
    for name in names:
        value = str(tool_parameters.get(name) or "").strip()
        if not value:
            raise JiraAuthError(f"{name} is required.")
        values.append(value)
    return values


def clamp(value: Any, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(number, maximum))


# ── rich text ─────────────────────────────────────────────────────────


def rich_text(ctx: JiraContext, markdown: str) -> Any:
    """A description or comment body: Atlassian Document Format on Cloud (v3), plain wiki text on Server (v2)."""
    if not ctx.cloud:
        return markdown
    from utils.md2adf import markdown_to_adf

    return markdown_to_adf(markdown)


def adf_to_text(node: Any) -> str:
    """Plain text of an ADF document (Cloud) or the string itself (Server), for tool output."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, Mapping):
        return ""
    kind = node.get("type")
    if kind == "text":
        return node.get("text", "")
    if kind == "hardBreak":
        return "\n"
    if kind in ("mention", "emoji"):
        attrs = node.get("attrs") or {}
        return attrs.get("text") or attrs.get("shortName") or ""
    if kind == "inlineCard":
        return (node.get("attrs") or {}).get("url", "")
    inner = "".join(adf_to_text(child) for child in node.get("content") or [])
    if kind in ("paragraph", "heading", "listItem", "codeBlock", "blockquote", "rule"):
        return inner.rstrip("\n") + "\n"
    return inner


# ── Jira objects ──────────────────────────────────────────────────────


def user_dict(user: Mapping[str, Any] | None) -> dict[str, Any]:
    user = user or {}
    return {
        # Cloud identifies people by accountId; Server by name/key.
        "account_id": user.get("accountId") or user.get("name") or user.get("key") or "",
        "display_name": user.get("displayName", ""),
        "email": user.get("emailAddress", ""),
        "active": bool(user.get("active", True)),
    }


def issue_dict(ctx: JiraContext, issue: Mapping[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    key = issue.get("key", "")
    return {
        "id": str(issue.get("id", "")),
        "key": key,
        "summary": fields.get("summary") or "",
        "status": (fields.get("status") or {}).get("name", ""),
        "issue_type": (fields.get("issuetype") or {}).get("name", ""),
        "priority": (fields.get("priority") or {}).get("name", ""),
        "assignee": (fields.get("assignee") or {}).get("displayName", ""),
        "reporter": (fields.get("reporter") or {}).get("displayName", ""),
        "project": (fields.get("project") or {}).get("key", ""),
        "labels": list(fields.get("labels") or []),
        "created": fields.get("created") or "",
        "updated": fields.get("updated") or "",
        "due_date": fields.get("duedate") or "",
        "description": adf_to_text(fields.get("description")).strip(),
        "url": ctx.browse(key),
    }


def comment_dict(comment: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(comment.get("id", "")),
        "author": (comment.get("author") or {}).get("displayName", ""),
        "body": adf_to_text(comment.get("body")).strip(),
        "created": comment.get("created", ""),
        "updated": comment.get("updated", ""),
    }


def attachment_dict(attachment: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(attachment.get("id", "")),
        "filename": attachment.get("filename", ""),
        "mime_type": attachment.get("mimeType", ""),
        "size": int(attachment.get("size") or 0),
        "author": (attachment.get("author") or {}).get("displayName", ""),
        "created": attachment.get("created", ""),
    }
