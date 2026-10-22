"""
Shared Microsoft Graph plumbing for the Outlook tools.

The plugin accepts two kinds of credentials:

- OAuth (delegated): a user signs in, the token acts as that user and every
  call goes to ``/me``.
- Service Principal (app-only): tenant ID + client ID + client secret, exchanged
  with the client-credentials grant. There is no signed-in user, so calls go to
  ``/users/{mailbox}`` and the target mailbox must be named.

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
    plugin process, so a workflow that calls several Outlook tools does not hit
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
    # Root of the mailbox the tools act on: {api_base}/me or {api_base}/users/{mailbox}
    mailbox_base: str


def resolve_graph_context(credentials: Mapping[str, Any], mailbox: Any = None) -> GraphContext:
    """
    Turn the runtime credentials (plus the optional per-tool Mailbox parameter)
    into a token and the URL roots every tool builds its requests on.
    """
    mailbox = setting_value(mailbox)

    if is_service_principal(credentials):
        _, graph_host = cloud_hosts(credentials.get("cloud"))
        token = acquire_app_token(
            credentials.get("tenant_id", ""),
            credentials.get("client_id", ""),
            credentials.get("client_secret", ""),
            credentials.get("cloud"),
        )
        target = mailbox or (credentials.get("mailbox") or "").strip()
        if not target:
            raise GraphAuthError(
                "A Service Principal has no signed-in user. Set a default mailbox on the credential "
                "or fill in the tool's Mailbox parameter (a user principal name such as support@contoso.com)."
            )
        api_base = f"{graph_host}/v1.0"
        return GraphContext(token, api_base, f"{api_base}/users/{quote(target, safe='@.')}")

    token = credentials.get("access_token")
    if not token:
        raise GraphAuthError("Access token is required in credentials.")
    if mailbox:
        raise GraphAuthError(
            "The Mailbox parameter only works with a Service Principal credential. "
            "With OAuth sign-in the tools always act on the signed-in user's own mailbox."
        )
    # Credentials authorized before national-cloud support have no graph_base_url: they are global.
    graph_host = (credentials.get("graph_base_url") or CLOUDS[DEFAULT_CLOUD][1]).rstrip("/")
    if graph_host not in {host for _, host in CLOUDS.values()}:
        # Never send the bearer token to a host that is not a Microsoft Graph endpoint.
        raise GraphAuthError(f"Unsupported Microsoft Graph endpoint '{graph_host}'.")
    api_base = f"{graph_host}/v1.0"
    return GraphContext(token, api_base, f"{api_base}/me")


def segment(value: Any) -> str:
    """Quote an ID for use as one URL path segment (calendar IDs can contain '/', '+' and '=')."""
    return quote(str(value).strip(), safe="")


def describe_error(response: requests.Response) -> str:
    """Turn a Graph error response into a short message with a hint for the common cases."""
    try:
        error = response.json().get("error") or {}
        detail = f"{error.get('code', '')}: {error.get('message', '')}".strip(": ")
    except ValueError:
        detail = response.text[:300]
    hint = {
        401: "Authentication failed; the token may be expired.",
        403: "Access denied: check the calendar permissions (Calendars.Read.Shared for calendars shared with you) and admin consent.",
        404: "Not found: check the IDs (get them from List Calendar Groups / List Calendars).",
    }.get(response.status_code, "")
    return f"API error {response.status_code}: {detail}" + (f" {hint}" if hint else "")


def calendars_in_group(ctx: GraphContext, group_id: str) -> list[dict[str, Any]]:
    """
    The calendars in a calendar group, each with its owner.

    The "People's calendars" group is where Outlook puts calendars other people
    shared with the user, so this is how an agent finds e.g. executives' calendars.
    """
    try:
        response = requests.get(
            f"{ctx.mailbox_base}/calendarGroups/{segment(group_id)}/calendars",
            headers={"Authorization": f"Bearer {ctx.access_token}"},
            params={"$select": "id,name,owner,canEdit,isDefaultCalendar", "$top": 100},
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        raise GraphAuthError(f"Network error: {e}") from e
    if response.status_code < 200 or response.status_code >= 300:
        raise GraphAuthError(describe_error(response))
    return response.json().get("value", [])


def calendar_tag(calendar: Mapping[str, Any]) -> dict[str, Any]:
    """Which calendar (and whose) an event came from, attached to merged results."""
    owner = calendar.get("owner") or {}
    return {
        "id": calendar.get("id"),
        "name": calendar.get("name"),
        "owner_name": owner.get("name"),
        "owner_address": owner.get("address"),
    }
