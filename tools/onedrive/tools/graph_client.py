"""
Shared Microsoft Graph plumbing for the OneDrive tools.

The plugin accepts two kinds of credentials:

- OAuth (delegated): a user signs in, the token acts as that user and every
  call goes to ``/me/drive``.
- Service Principal (app-only): tenant ID + client ID + client secret, exchanged
  with the client-credentials grant. There is no signed-in user, so calls go to
  ``/users/{user}/drive`` and the drive owner must be named.

Both kinds can target a national cloud; the login host and the Graph host are
looked up together from ``CLOUDS`` so they never point at different clouds.
"""

import ast
import hashlib
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

import requests

# cloud -> (Entra login host, Microsoft Graph host)
CLOUDS: dict[str, tuple[str, str]] = {
    "global": ("https://login.microsoftonline.com", "https://graph.microsoft.com"),
    "usgov": ("https://login.microsoftonline.us", "https://graph.microsoft.us"),
    "dod": ("https://login.microsoftonline.us", "https://dod-graph.microsoft.us"),
    "china": ("https://login.partner.microsoftonline.cn", "https://microsoftgraph.chinacloudapi.cn"),
}
DEFAULT_CLOUD = "global"

# Refresh a cached app-only token this many seconds before it expires.
_EXPIRY_MARGIN = 300

_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()


class GraphAuthError(Exception):
    """Raised when credentials cannot be turned into a usable Graph call."""


# repr() of the workflow editor's {"value": ..., "type": ...} wrapper for a tool setting
_WRAPPED_SETTING = re.compile(
    r"""^\{'value':\s*(?P<value>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"),\s*'type':\s*<ToolInputType\.[A-Z_]+:\s*'[a-z_]+'>\}$"""
)


def setting_value(value: Any) -> str:
    """
    Plain string value of a form-type tool setting.

    The workflow editor stores settings as {"type": "constant", "value": ...}. Dify 1.16.1
    hands string settings to the plugin as the repr() of that wrapper instead of the value,
    e.g. "{'value': 'a@contoso.com', 'type': <ToolInputType.CONSTANT: 'constant'>}", so
    unwrap both the mapping and its repr.
    """
    if isinstance(value, Mapping):
        value = value.get("value")
    if value is None:
        return ""
    text = str(value).strip()
    match = _WRAPPED_SETTING.match(text)
    if match:
        text = str(ast.literal_eval(match.group("value"))).strip()
    return text


def cloud_hosts(cloud: str | None) -> tuple[str, str]:
    """Return (login host, Graph host) for a cloud name; unknown names are rejected."""
    name = (cloud or DEFAULT_CLOUD).strip().lower()
    if name not in CLOUDS:
        raise GraphAuthError(f"Unknown Microsoft cloud '{cloud}'. Use one of: {', '.join(CLOUDS)}.")
    return CLOUDS[name]


def is_service_principal(credentials: Mapping[str, Any]) -> bool:
    """Service Principal credentials carry a client secret; OAuth credentials carry an access token."""
    return bool(credentials.get("client_secret")) and not credentials.get("access_token")


def acquire_app_token(tenant_id: str, client_id: str, client_secret: str, cloud: str | None = None) -> str:
    """
    Get an app-only Graph token with the client-credentials grant.

    Tokens are cached per (cloud, tenant, client, secret) for the life of the
    plugin process, so a workflow that calls several OneDrive tools does not hit
    the token endpoint each time.
    """
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
    if "/" in tenant_id or "?" in tenant_id or "#" in tenant_id or " " in tenant_id:
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
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": f"{graph_host}/.default",
            },
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
    expires_at = time.time() + int(payload.get("expires_in", 3599))

    with _token_lock:
        _token_cache[cache_key] = (token, expires_at)
    return token


@dataclass(frozen=True)
class GraphContext:
    access_token: str
    # Graph v1.0 root, e.g. https://graph.microsoft.com/v1.0
    api_base: str
    # Root of the drive the tools act on: {api_base}/me/drive or {api_base}/users/{user}/drive
    drive_base: str


def resolve_graph_context(credentials: Mapping[str, Any], drive_user: Any = None) -> GraphContext:
    """
    Turn the runtime credentials (plus the optional per-tool Drive Owner parameter)
    into a token and the URL roots every tool builds its requests on.
    """
    drive_user = setting_value(drive_user)

    if is_service_principal(credentials):
        _, graph_host = cloud_hosts(credentials.get("cloud"))
        token = acquire_app_token(
            credentials.get("tenant_id", ""),
            credentials.get("client_id", ""),
            credentials.get("client_secret", ""),
            credentials.get("cloud"),
        )
        target = drive_user or (credentials.get("drive_user") or "").strip()
        if not target:
            raise GraphAuthError(
                "A Service Principal has no signed-in user. Set a default drive owner on the credential "
                "or fill in the tool's Drive Owner parameter (a user principal name such as alice@contoso.com)."
            )
        api_base = f"{graph_host}/v1.0"
        return GraphContext(token, api_base, f"{api_base}/users/{quote(target, safe='@.')}/drive")

    token = credentials.get("access_token")
    if not token:
        raise GraphAuthError("Access token is required in credentials.")
    if drive_user:
        raise GraphAuthError(
            "The Drive Owner parameter only works with a Service Principal credential. "
            "With OAuth sign-in the tools always act on the signed-in user's own OneDrive."
        )
    # Credentials authorized before national-cloud support have no graph_base_url: they are global.
    graph_host = (credentials.get("graph_base_url") or CLOUDS[DEFAULT_CLOUD][1]).rstrip("/")
    if graph_host not in {host for _, host in CLOUDS.values()}:
        # Never send the bearer token to a host that is not a Microsoft Graph endpoint.
        raise GraphAuthError(f"Unsupported Microsoft Graph endpoint '{graph_host}'.")
    api_base = f"{graph_host}/v1.0"
    return GraphContext(token, api_base, f"{api_base}/me/drive")


def segment(value: Any) -> str:
    """Quote a drive item ID for use as one URL path segment."""
    return quote(str(value).strip(), safe="")


def graph_request(
    ctx: GraphContext,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    data: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: int = 60,
) -> requests.Response:
    """Call a Graph URL with the context's token; network errors and non-2xx answers raise GraphAuthError."""
    all_headers = {"Authorization": f"Bearer {ctx.access_token}"}
    all_headers.update(headers or {})
    try:
        response = requests.request(method, url, headers=all_headers, params=params, data=data, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise GraphAuthError(f"Network error: {e}") from e
    if response.status_code < 200 or response.status_code >= 300:
        raise GraphAuthError(describe_error(response))
    return response


def describe_error(response: requests.Response) -> str:
    """Turn a Graph error response into a short message with a hint for the common cases."""
    try:
        error = response.json().get("error") or {}
        detail = f"{error.get('code', '')}: {error.get('message', '')}".strip(": ")
    except ValueError:
        detail = response.text[:300]
    hint = {
        401: "The sign-in has expired or the token is invalid; re-authorize the plugin.",
        403: "Access denied: check the Files permissions (and admin consent for a Service Principal).",
        404: "Not found: check the file ID, or that the drive owner has a OneDrive.",
        429: "Microsoft Graph is throttling requests; wait a moment and retry.",
    }.get(response.status_code, "")
    return f"OneDrive API error {response.status_code}: {detail}" + (f" {hint}" if hint else "")


def file_info(item: Mapping[str, Any]) -> dict[str, Any]:
    """The fields the tools return for a drive item (the same keys the tools returned before)."""
    parent = item.get("parentReference") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "size": item.get("size"),  # In bytes
        "download_url": item.get("@microsoft.graph.downloadUrl"),
        "created_date_time": item.get("createdDateTime"),
        "last_modified_date_time": item.get("lastModifiedDateTime"),
        "path": parent.get("path"),
        "drive_id": parent.get("driveId"),
        "web_url": item.get("webUrl"),
    }
