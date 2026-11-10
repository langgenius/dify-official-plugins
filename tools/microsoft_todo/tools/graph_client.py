"""
Shared Microsoft Graph plumbing for the To Do tools.

The plugin accepts three kinds of credentials:

- OAuth (delegated): a user signs in from the Dify console; the token acts as that user
  and the tools use ``/me/todo``. Authorizations made before 1.0.0 stored the whole token
  as JSON text under ``token``; they keep working.
- Service Principal (app-only): tenant ID + client ID + client secret, exchanged with the
  client-credentials grant. There is no signed-in user, so the tasks' owner must be named
  and the tools use ``/users/{user}/todo``.
- Each user signs in (delegated, per chat user): the same app fields plus
  ``auth_mode: per_user``; every Dify user gets their own token (see ``user_auth``).

Every kind can target a national cloud; the login host and the Graph host are looked up
together from ``CLOUDS``. Every ID that goes into a URL is encoded here, so an ID chosen by
the model cannot change the request path.
"""

import ast
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote

import requests

from tools.user_auth import SignInRequired, UserAuthError, UserSignIn

# cloud -> (Entra login host, Microsoft Graph host)
CLOUDS: dict[str, tuple[str, str]] = {
    "global": ("https://login.microsoftonline.com", "https://graph.microsoft.com"),
    "usgov": ("https://login.microsoftonline.us", "https://graph.microsoft.us"),
    "dod": ("https://login.microsoftonline.us", "https://dod-graph.microsoft.us"),
    "china": ("https://login.partner.microsoftonline.cn", "https://microsoftgraph.chinacloudapi.cn"),
}
DEFAULT_CLOUD = "global"
GRAPH_HOSTS = {host for _, host in CLOUDS.values()}

# Refresh a cached app-only token this many seconds before it expires.
_EXPIRY_MARGIN = 300

_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()


class GraphAuthError(Exception):
    """A Graph call that could not be made or did not succeed; the message is shown to the user."""


# repr() of the workflow editor's {"value": ..., "type": ...} wrapper for a tool setting
_WRAPPED_SETTING = re.compile(
    r"""^\{'value':\s*(?P<value>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"),\s*'type':\s*<ToolInputType\.[A-Z_]+:\s*'[a-z_]+'>\}$"""
)


def setting_value(value: Any) -> str:
    """The plain value of a tool setting (it can arrive as the editor's {"type", "value"} wrapper or its repr())."""
    if value is None:
        return ""
    if isinstance(value, Mapping):
        return str(value.get("value") or "").strip()
    text = str(value).strip()
    match = _WRAPPED_SETTING.match(text)
    if match:
        return str(ast.literal_eval(match.group("value"))).strip()
    return text


def cloud_hosts(cloud: str | None) -> tuple[str, str]:
    """Return (login host, Graph host) for a cloud name; unknown names are rejected."""
    name = (cloud or DEFAULT_CLOUD).strip().lower()
    if name not in CLOUDS:
        raise GraphAuthError(f"Unknown Microsoft cloud '{cloud}'. Use one of: {', '.join(CLOUDS)}.")
    return CLOUDS[name]


def legacy_token(credentials: Mapping[str, Any]) -> dict[str, Any]:
    """The token of an OAuth authorization made before 1.0.0 (JSON text under ``token``), or {}."""
    raw = credentials.get("token")
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def oauth_access_token(credentials: Mapping[str, Any]) -> str:
    return credentials.get("access_token") or legacy_token(credentials).get("access_token") or ""


def is_per_user(credentials: Mapping[str, Any]) -> bool:
    """An app credential set to "Each user signs in"; app credentials saved without a mode are Service Principal."""
    return credentials.get("auth_mode") == "per_user" and not oauth_access_token(credentials)


def is_service_principal(credentials: Mapping[str, Any]) -> bool:
    """Service Principal credentials carry a client secret and no token; OAuth credentials carry a token."""
    return (
        bool(credentials.get("client_secret"))
        and bool(credentials.get("tenant_id"))
        and not oauth_access_token(credentials)
        and not is_per_user(credentials)
    )


def acquire_app_token(tenant_id: str, client_id: str, client_secret: str, cloud: str | None = None) -> str:
    """App-only Graph token (client-credentials grant), cached per (cloud, tenant, client, secret)."""
    tenant_id = (tenant_id or "").strip()
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    if not tenant_id or not client_id or not client_secret:
        raise GraphAuthError("Tenant ID, Client ID and Client Secret are all required.")
    if tenant_id.lower() in ("common", "organizations", "consumers"):
        raise GraphAuthError(
            "A Service Principal needs your directory's own Tenant ID (a GUID or a domain such as "
            "contoso.onmicrosoft.com), not 'common', 'organizations' or 'consumers'."
        )
    if any(c in tenant_id for c in "/?# "):
        raise GraphAuthError("Tenant ID must be a GUID or a domain name.")

    login_host, graph_host = cloud_hosts(cloud)
    secret_hash = hashlib.sha256(client_secret.encode("utf-8")).hexdigest()
    cache_key = f"{login_host}|{tenant_id}|{client_id}|{secret_hash}"
    with _token_lock:
        cached = _token_cache.get(cache_key)
        if cached and cached[1] - _EXPIRY_MARGIN > time.time():
            return cached[0]
    try:
        response = requests.post(
            f"{login_host}/{tenant_id}/oauth2/v2.0/token",
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret,
                  "scope": f"{graph_host}/.default"},
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        raise GraphAuthError(f"Could not reach Microsoft Entra ID: {e}") from e
    if response.status_code != 200:
        try:
            payload = response.json()
            detail = payload.get("error_description") or payload.get("error") or response.text
        except ValueError:
            detail = response.text
        raise GraphAuthError(f"Service Principal sign-in failed ({response.status_code}): {detail}")
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise GraphAuthError("Microsoft Entra ID returned no access token.")
    with _token_lock:
        _token_cache[cache_key] = (token, time.time() + int(payload.get("expires_in", 3599)))
    return token


def segment(value: Any) -> str:
    """Quote an ID for use as one URL path segment."""
    return quote(str(value).strip(), safe="")


@dataclass(frozen=True)
class GraphContext:
    access_token: str
    # Graph v1.0 root, e.g. https://graph.microsoft.com/v1.0
    api_base: str
    # Root of the To Do data the tools work on: /me/todo or /users/{user}/todo
    todo_base: str

    def lists(self) -> str:
        return f"{self.todo_base}/lists"

    def task_list(self, list_id: Any) -> str:
        return f"{self.todo_base}/lists/{segment(list_id)}"

    def tasks(self, list_id: Any) -> str:
        return f"{self.task_list(list_id)}/tasks"

    def task(self, list_id: Any, task_id: Any) -> str:
        return f"{self.tasks(list_id)}/{segment(task_id)}"

    def linked_resources(self, list_id: Any, task_id: Any) -> str:
        return f"{self.task(list_id, task_id)}/linkedResources"

    def linked_resource(self, list_id: Any, task_id: Any, resource_id: Any) -> str:
        return f"{self.linked_resources(list_id, task_id)}/{segment(resource_id)}"


def resolve_graph_context(credentials: Mapping[str, Any], tool: Any = None, task_user: Any = None) -> GraphContext:
    """
    Turn the runtime credentials, plus the tool's optional Task Owner setting, into a token and
    the To Do root the tools work on. ``tool`` is the calling Tool; per-user sign-in needs its
    user ID and plugin storage. When that user has not signed in yet, the error is the sign-in link.
    """
    task_user = setting_value(task_user)

    if is_per_user(credentials) or is_service_principal(credentials):
        _, graph_host = cloud_hosts(credentials.get("cloud"))
        api_base = f"{graph_host}/v1.0"
        if is_per_user(credentials):
            if task_user:
                raise GraphAuthError(
                    "The Task Owner setting only works with a Service Principal credential. "
                    "With per-user sign-in the tools use the calling user's own tasks."
                )
            if tool is None:
                raise GraphAuthError("Per-user sign-in is not available here.")
            return GraphContext(user_access_token(credentials, tool), api_base, f"{api_base}/me/todo")
        token = acquire_app_token(
            credentials.get("tenant_id", ""), credentials.get("client_id", ""),
            credentials.get("client_secret", ""), credentials.get("cloud"),
        )
        owner = task_user or (credentials.get("task_user") or "").strip()
        if not owner:
            raise GraphAuthError(
                "A Service Principal has no signed-in user. Set a default Task Owner on the credential or "
                "fill in the tool's Task Owner setting (a user principal name such as alice@contoso.com)."
            )
        return GraphContext(token, api_base, f"{api_base}/users/{quote(owner, safe='@.')}/todo")

    token = oauth_access_token(credentials)
    if not token:
        raise GraphAuthError("Access token is missing. Please authorize the plugin first.")
    if task_user:
        raise GraphAuthError(
            "The Task Owner setting only works with a Service Principal credential. "
            "With OAuth sign-in the tools use the signed-in user's own tasks."
        )
    # Authorizations made before national-cloud support have no graph_base_url: they are global.
    graph_host = (credentials.get("graph_base_url") or CLOUDS[DEFAULT_CLOUD][1]).rstrip("/")
    if graph_host not in GRAPH_HOSTS:
        # Never send the bearer token to a host that is not a Microsoft Graph endpoint.
        raise GraphAuthError(f"Unsupported Microsoft Graph endpoint '{graph_host}'.")
    api_base = f"{graph_host}/v1.0"
    return GraphContext(token, api_base, f"{api_base}/me/todo")


def user_sign_in(credentials: Mapping[str, Any], tool: Any) -> "UserSignIn":
    login_host, graph_host = cloud_hosts(credentials.get("cloud"))
    try:
        return UserSignIn(
            credentials, tool.runtime.user_id, tool.session.storage, login_host, graph_host, CLOUDS[DEFAULT_CLOUD][1]
        )
    except UserAuthError as e:
        raise GraphAuthError(str(e)) from e


def user_access_token(credentials: Mapping[str, Any], tool: Any) -> str:
    sign_in = user_sign_in(credentials, tool)
    try:
        token = sign_in.access_token()
    except (SignInRequired, UserAuthError) as e:
        raise GraphAuthError(str(e)) from e
    if sign_in.just_signed_in:
        # @with_outputs tells the user which account they signed in with.
        tool._signed_in_as = sign_in.just_signed_in
    return token


def context_for(tool: Any, tool_parameters: Mapping[str, Any]) -> GraphContext:
    return resolve_graph_context(tool.runtime.credentials, tool, tool_parameters.get("task_user"))


def graph_request(
    ctx: GraphContext, method: str, url: str, *, params: Mapping[str, Any] | None = None,
    json_body: Any = None, timeout: int = 30,
) -> requests.Response:
    """Call a Graph URL with the context's token; network errors and non-2xx answers raise GraphAuthError."""
    headers = {"Authorization": f"Bearer {ctx.access_token}", "Accept": "application/json"}
    extra = {"json": json_body} if json_body is not None else {}
    try:
        response = requests.request(method, url, headers=headers, params=params, timeout=timeout, **extra)
    except requests.exceptions.RequestException as e:
        raise GraphAuthError(f"Network error: {e}") from e
    if response.status_code < 200 or response.status_code >= 300:
        raise GraphAuthError(describe_error(response))
    return response


def get_all(ctx: GraphContext, url: str, params: Mapping[str, Any] | None, limit: int) -> list[dict[str, Any]]:
    """Up to ``limit`` items, following @odata.nextLink (only on the Graph host, so the token never goes elsewhere)."""
    items: list[dict[str, Any]] = []
    next_url: str | None = url
    while next_url and len(items) < limit:
        body = graph_request(ctx, "GET", next_url, params=params).json()
        items.extend(body.get("value", []))
        params = None
        next_url = body.get("@odata.nextLink")
        if next_url and not next_url.startswith(ctx.api_base + "/"):
            next_url = None
    return items[:limit]


def describe_error(response: requests.Response) -> str:
    try:
        error = response.json().get("error") or {}
        detail = f"{error.get('code', '')}: {error.get('message', '')}".strip(": ")
    except ValueError:
        detail = response.text[:300]
    hint = {
        401: "The sign-in has expired or the token is invalid; re-authorize the plugin.",
        403: "Access denied: check the Tasks permissions (and admin consent for a Service Principal).",
        404: "Not found: check the list, task or linked resource ID (get them from the list tools).",
        429: "Microsoft Graph is throttling requests; wait a moment and retry.",
    }.get(response.status_code, "")
    return f"To Do API error {response.status_code}: {detail}" + (f" {hint}" if hint else "")


def require(tool_parameters: Mapping[str, Any], *names: str) -> list[str]:
    values = []
    for name in names:
        value = str(tool_parameters.get(name) or "").strip()
        if not value:
            raise GraphAuthError(f"{name} is required.")
        values.append(value)
    return values


# ── task fields ───────────────────────────────────────────────────────


def graph_datetime(value: Any, name: str) -> dict[str, str]:
    """
    A dateTimeTimeZone from "YYYY-MM-DD" or an ISO 8601 date-time. A value with a UTC offset is
    converted to UTC; one without is taken as UTC.
    """
    text = str(value).strip()
    try:
        if len(text) == 10:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as e:
        raise GraphAuthError(f"{name} must be a date (YYYY-MM-DD) or an ISO 8601 date-time.") from e
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return {"dateTime": parsed.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"}


def _dt_text(value: Any) -> str:
    """A Graph dateTimeTimeZone as "YYYY-MM-DD HH:MM:SS+00:00" (the form the tools returned before 1.0.0)."""
    if not isinstance(value, Mapping) or not value.get("dateTime"):
        return ""
    raw = str(value["dateTime"])
    try:
        parsed = datetime.fromisoformat(raw[:26])
    except ValueError:
        return raw
    if str(value.get("timeZone") or "UTC").upper() in ("UTC", "ETC/UTC"):
        parsed = parsed.replace(tzinfo=timezone.utc)
    return str(parsed)


# "2026-10-30T01:02:03.1234567Z": Graph writes 7 fractional digits, Python reads at most 6.
_ISO = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)?$")


def _created_text(value: Any) -> str:
    """createdDateTime (UTC) as "YYYY-MM-DD HH:MM:SS.ffffff+00:00" (the form the tools returned before 1.0.0)."""
    match = _ISO.match(str(value or "").strip())
    if not match:
        return str(value or "")
    base, fraction, offset = match.groups()
    text = base + (f".{fraction[:6]}" if fraction else "") + ("+00:00" if offset in (None, "Z") else offset)
    return str(datetime.fromisoformat(text).astimezone(timezone.utc))


def task_dict(task: Mapping[str, Any]) -> dict[str, Any]:
    """A task in the shape the tools returned before 1.0.0, plus importance and reminder."""
    return {
        "task_id": task.get("id", ""),
        "title": task.get("title", ""),
        "status": task.get("status", ""),
        "body_text": (task.get("body") or {}).get("content") or "",
        "due_date": _dt_text(task.get("dueDateTime")),
        "created_date": _created_text(task.get("createdDateTime")),
        "importance": task.get("importance", ""),
        "reminder": _dt_text(task.get("reminderDateTime")) if task.get("isReminderOn", True) else "",
    }


def list_dict(task_list: Mapping[str, Any]) -> dict[str, Any]:
    """A task list in the shape the tools returned before 1.0.0."""
    list_id = task_list.get("id", "")
    return {
        "list_id": list_id,
        "display_name": task_list.get("displayName", ""),
        "is_owner": bool(task_list.get("isOwner")),
        "is_shared": bool(task_list.get("isShared")),
        "link": f"href=https://to-do.live.com/tasks/{list_id}",
    }


def resource_dict(resource: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "linked_resource_id": resource.get("id", ""),
        "display_name": resource.get("displayName") or "",
        "application_name": resource.get("applicationName") or "",
        "external_id": resource.get("externalId") or "",
        "web_url": resource.get("webUrl") or "",
    }


TASK_STATUSES = ("notStarted", "inProgress", "completed", "waitingOnOthers", "deferred")
IMPORTANCES = ("low", "normal", "high")


def task_fields(tool_parameters: Mapping[str, Any], *, for_update: bool) -> dict[str, Any]:
    """The Graph body for the optional task fields that were given."""
    body: dict[str, Any] = {}
    title = str(tool_parameters.get("title") or "").strip()
    if title and for_update:
        body["title"] = title
    content = tool_parameters.get("body_text")
    if content not in (None, ""):
        body["body"] = {"content": str(content), "contentType": "text"}
    due = str(tool_parameters.get("due_date") or "").strip()
    if due:
        body["dueDateTime"] = graph_datetime(due, "due_date")
    reminder = str(tool_parameters.get("reminder_datetime") or "").strip()
    if reminder:
        body["reminderDateTime"] = graph_datetime(reminder, "reminder_datetime")
        body["isReminderOn"] = True
    importance = str(tool_parameters.get("importance") or "").strip()
    if importance:
        if importance not in IMPORTANCES:
            raise GraphAuthError(f"importance must be one of: {', '.join(IMPORTANCES)}.")
        body["importance"] = importance
    status = str(tool_parameters.get("status") or "").strip()
    if status:
        if status not in TASK_STATUSES:
            raise GraphAuthError(f"status must be one of: {', '.join(TASK_STATUSES)}.")
        body["status"] = status
    return body
