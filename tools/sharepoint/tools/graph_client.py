"""
Shared Microsoft Graph plumbing for the SharePoint tools.

The plugin accepts three kinds of credentials:

- OAuth (delegated): a user signs in from the Dify console; the token acts as that user.
- Service Principal (app-only): tenant ID + client ID + client secret, exchanged with the
  client-credentials grant. Sites are tenant resources, so no user has to be named.
- Each user signs in (delegated, per chat user): the same app fields plus
  ``auth_mode: per_user``; every Dify user gets their own token (see ``user_auth``).

Every kind can target a national cloud; the login host and the Graph host are looked up
together from ``CLOUDS``. A site can be given as its Graph ID ("host,site-guid,web-guid"),
its URL ("https://contoso.sharepoint.com/sites/Team") or "root"; every other ID that goes
into a URL is encoded here, so an ID chosen by the model cannot change the request path.
"""

import ast
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote, unquote, urlparse

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


def is_per_user(credentials: Mapping[str, Any]) -> bool:
    """An app credential set to "Each user signs in"; app credentials saved without a mode are Service Principal."""
    return credentials.get("auth_mode") == "per_user" and not credentials.get("access_token")


def is_service_principal(credentials: Mapping[str, Any]) -> bool:
    """Service Principal credentials carry a client secret and no token; OAuth credentials carry a token."""
    return (
        bool(credentials.get("client_secret"))
        and bool(credentials.get("tenant_id"))
        and not credentials.get("access_token")
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

    def site(self, site_id: str) -> str:
        return f"{self.api_base}/sites/{site_segment(site_id)}"

    def lists(self, site_id: str) -> str:
        return f"{self.site(site_id)}/lists"

    def list(self, site_id: str, list_id: Any) -> str:
        return f"{self.lists(site_id)}/{segment(list_id)}"

    def items(self, site_id: str, list_id: Any) -> str:
        return f"{self.list(site_id, list_id)}/items"

    def item(self, site_id: str, list_id: Any, item_id: Any) -> str:
        return f"{self.items(site_id, list_id)}/{segment(item_id)}"

    def drive_item(self, site_id: str, item_id: Any) -> str:
        """A file or folder in the site's default document library; empty or "root" is its root folder."""
        value = str(item_id or "").strip()
        base = f"{self.site(site_id)}/drive"
        return f"{base}/root" if value in ("", "root") else f"{base}/items/{segment(value)}"


def site_segment(site_id: Any) -> str:
    """A site's Graph ID ("host,site-guid,web-guid") as one path segment; Graph expects the commas as they are."""
    return quote(str(site_id).strip(), safe=",")


def resolve_graph_context(credentials: Mapping[str, Any], tool: Any = None) -> GraphContext:
    """
    Turn the runtime credentials into a token and the Graph v1.0 root. ``tool`` is the calling
    Tool; per-user sign-in needs its user ID and plugin storage. When that user has not signed
    in yet, the GraphAuthError message is the sign-in link.
    """
    if is_per_user(credentials) or is_service_principal(credentials):
        _, graph_host = cloud_hosts(credentials.get("cloud"))
        api_base = f"{graph_host}/v1.0"
        if is_per_user(credentials):
            if tool is None:
                raise GraphAuthError("Per-user sign-in is not available here.")
            return GraphContext(user_access_token(credentials, tool), api_base)
        token = acquire_app_token(
            credentials.get("tenant_id", ""), credentials.get("client_id", ""),
            credentials.get("client_secret", ""), credentials.get("cloud"),
        )
        return GraphContext(token, api_base)

    token = credentials.get("access_token")
    if not token:
        raise GraphAuthError("Access token is missing. Please authorize the plugin first.")
    # Authorizations made before national-cloud support have no graph_base_url: they are global.
    graph_host = (credentials.get("graph_base_url") or CLOUDS[DEFAULT_CLOUD][1]).rstrip("/")
    if graph_host not in GRAPH_HOSTS:
        # Never send the bearer token to a host that is not a Microsoft Graph endpoint.
        raise GraphAuthError(f"Unsupported Microsoft Graph endpoint '{graph_host}'.")
    return GraphContext(token, f"{graph_host}/v1.0")


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
    return resolve_graph_context(tool.runtime.credentials, tool)


def graph_request(
    ctx: GraphContext, method: str, url: str, *, params: Mapping[str, Any] | None = None,
    json_body: Any = None, data: bytes | None = None, headers: Mapping[str, str] | None = None, timeout: int = 30,
) -> requests.Response:
    """Call a Graph URL with the context's token; network errors and non-2xx answers raise GraphAuthError."""
    all_headers = {"Authorization": f"Bearer {ctx.access_token}", "Accept": "application/json", **(headers or {})}
    headers = all_headers
    extra: dict[str, Any] = {"json": json_body} if json_body is not None else {}
    if data is not None:
        extra["data"] = data
    try:
        response = requests.request(method, url, headers=headers, params=params, timeout=timeout, **extra)
    except requests.exceptions.RequestException as e:
        raise GraphAuthError(f"Network error: {e}") from e
    if response.status_code < 200 or response.status_code >= 300:
        raise GraphAuthError(describe_error(response))
    return response


def get_all(
    ctx: GraphContext, url: str, params: Mapping[str, Any] | None, limit: int, headers: Mapping[str, str] | None = None
) -> list[dict[str, Any]]:
    """Up to ``limit`` items, following @odata.nextLink (only on the Graph host, so the token never goes elsewhere)."""
    items: list[dict[str, Any]] = []
    next_url: str | None = url
    while next_url and len(items) < limit:
        body = graph_request(ctx, "GET", next_url, params=params, headers=headers).json()
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
        403: "Access denied: check the Sites permissions (and admin consent, or a Sites.Selected grant, for a Service Principal).",
        404: "Not found: check the site, list, item or file ID (get them from the search and list tools).",
        429: "Microsoft Graph is throttling requests; wait a moment and retry.",
    }.get(response.status_code, "")
    return f"SharePoint API error {response.status_code}: {detail}" + (f" {hint}" if hint else "")


def require(tool_parameters: Mapping[str, Any], *names: str) -> list[str]:
    values = []
    for name in names:
        value = str(tool_parameters.get(name) or "").strip()
        if not value:
            raise GraphAuthError(f"{name} is required.")
        values.append(value)
    return values


# ── SharePoint objects ────────────────────────────────────────────────


def resolve_site(ctx: GraphContext, site: Any) -> dict[str, Any]:
    """
    The site for a Site parameter: its Graph ID ("host,site-guid,web-guid"), its URL
    ("https://contoso.sharepoint.com/sites/Team") or "root" (the tenant's root site).
    """
    value = str(site or "").strip()
    if not value:
        raise GraphAuthError("site is required: a site URL, its ID, or 'root'. Use the search sites tool to find one.")
    if value.lower().startswith(("https://", "http://")):
        parsed = urlparse(value)
        host = parsed.hostname or ""
        if not host.lower().endswith((".sharepoint.com", ".sharepoint.us", ".sharepoint.cn", ".sharepoint-mil.us")):
            raise GraphAuthError(f"'{host}' is not a SharePoint host; give a URL such as https://contoso.sharepoint.com/sites/Team.")
        # The site part of a URL is the path up to /sites/<name> or /teams/<name>; anything after it is a page or a file.
        parts = [p for p in unquote(parsed.path).split("/") if p]
        path = "/".join(parts[:2]) if len(parts) >= 2 and parts[0].lower() in ("sites", "teams") else ""
        url = f"{ctx.api_base}/sites/{quote(host, safe='')}" + (f":/{quote(path, safe='/')}:" if path else "")
    elif value.lower() == "root":
        url = f"{ctx.api_base}/sites/root"
    else:
        url = ctx.site(value)
    return site_dict(graph_request(ctx, "GET", url, params={"$select": "id,name,displayName,webUrl,description"}).json())


def site_dict(site: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "site_id": site.get("id", ""),
        "name": site.get("displayName") or site.get("name") or "",
        "web_url": site.get("webUrl", ""),
        "description": site.get("description") or "",
    }


def list_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    info = item.get("list") or {}
    return {
        "list_id": item.get("id", ""),
        "name": item.get("displayName") or item.get("name") or "",
        "description": item.get("description") or "",
        "template": info.get("template", ""),
        "web_url": item.get("webUrl", ""),
        "hidden": bool(info.get("hidden")),
    }


# Fields SharePoint adds to every item; left out of the simplified output.
_SYSTEM_FIELDS = {
    "@odata.etag", "ContentType", "_UIVersionString", "Attachments", "Edit", "LinkTitleNoMenu", "LinkTitle",
    "ItemChildCount", "FolderChildCount", "_ComplianceFlags", "_ComplianceTag", "_ComplianceTagWrittenTime",
    "_ComplianceTagUserId", "AppAuthorLookupId", "AppEditorLookupId", "AuthorLookupId", "EditorLookupId",
}


def item_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    fields = {k: v for k, v in (item.get("fields") or {}).items() if k not in _SYSTEM_FIELDS and not k.startswith("@odata")}
    return {
        "item_id": str(item.get("id", "")),
        "fields": fields,
        "web_url": item.get("webUrl", ""),
        "created": item.get("createdDateTime", ""),
        "modified": item.get("lastModifiedDateTime", ""),
    }


def file_dict(item: Mapping[str, Any]) -> dict[str, Any]:
    parent = item.get("parentReference") or {}
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "is_folder": "folder" in item,
        "size": int(item.get("size") or 0),
        "mime_type": (item.get("file") or {}).get("mimeType") or "",
        "web_url": item.get("webUrl", ""),
        "path": parent.get("path") or "",
        "last_modified": item.get("lastModifiedDateTime", ""),
    }


def parse_fields(value: Any, name: str = "fields") -> dict[str, Any]:
    """Item fields as a JSON object keyed by column name, e.g. {"Title": "Q3 report", "Status": "Draft"}."""
    if isinstance(value, Mapping):
        fields = dict(value)
    else:
        text = str(value or "").strip()
        if not text:
            raise GraphAuthError(f"{name} is required.")
        try:
            fields = json.loads(text)
        except ValueError as e:
            raise GraphAuthError(f'{name} must be a JSON object, e.g. {{"Title": "Q3 report", "Status": "Draft"}}.') from e
    if not isinstance(fields, dict) or not fields:
        raise GraphAuthError(f'{name} must be a non-empty JSON object keyed by column name, e.g. {{"Title": "Q3 report"}}.')
    return fields


def odata_literal(value: Any) -> str:
    """A value for an OData $filter: numbers and booleans as they are, text quoted."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"
