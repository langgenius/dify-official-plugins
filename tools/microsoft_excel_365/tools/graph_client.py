"""
Shared Microsoft Graph plumbing for the Excel tools.

The plugin accepts three kinds of credentials:

- OAuth (delegated): a user signs in from the Dify console; the token acts as that
  user and workbooks are found in ``/me/drive``.
- Service Principal (app-only): tenant ID + client ID + client secret, exchanged with
  the client-credentials grant. There is no signed-in user, so the drive must be named:
  a user's OneDrive (``/users/{user}/drive``) or a SharePoint site's (``/sites/{id}/drive``).
- Each user signs in (delegated, per chat user): the same app fields plus
  ``auth_mode: per_user``; every Dify user gets their own token (see ``user_auth``).

Every kind can target a national cloud; the login host and the Graph host are looked
up together from ``CLOUDS`` so they never point at different clouds. Every ID or name
that goes into a URL is encoded here, so a worksheet called ``Q3's`` or an ID chosen by
the model cannot change the request path.
"""

import ast
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
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
    """
    The plain value of a tool setting. A string typed in the workflow editor can arrive as
    the editor's {"type", "value"} wrapper, or as the repr() of it.
    """
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
    """Service Principal credentials carry a client secret; OAuth credentials carry an access token."""
    return bool(credentials.get("client_secret")) and not credentials.get("access_token") and not is_per_user(credentials)


def acquire_app_token(tenant_id: str, client_id: str, client_secret: str, cloud: str | None = None) -> str:
    """
    Get an app-only Graph token with the client-credentials grant, cached per
    (cloud, tenant, client, secret) for the life of the plugin process.
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
    with _token_lock:
        _token_cache[cache_key] = (token, time.time() + int(payload.get("expires_in", 3599)))
    return token


def segment(value: Any) -> str:
    """Quote an ID or name for use as one URL path segment."""
    return quote(str(value).strip(), safe="")


def site_segment(value: Any) -> str:
    """A SharePoint site ID ("host,site-guid,web-guid") as one path segment; Graph expects the commas as they are."""
    return quote(str(value).strip(), safe=",")


def odata_string(value: Any) -> str:
    """An OData string literal for a function parameter such as range(address='...'), URL-quoted."""
    return quote("'" + str(value).replace("'", "''") + "'", safe="")


@dataclass(frozen=True)
class GraphContext:
    access_token: str
    # Graph v1.0 root, e.g. https://graph.microsoft.com/v1.0
    api_base: str
    # Root of the drive the workbooks are in: /me/drive, /users/{user}/drive or /sites/{site}/drive
    drive_base: str

    def workbook(self, workbook_id: Any) -> str:
        return f"{self.drive_base}/items/{segment(workbook_id)}/workbook"

    def worksheet(self, workbook_id: Any, worksheet: Any) -> str:
        return f"{self.workbook(workbook_id)}/worksheets/{segment(worksheet)}"

    def range(self, workbook_id: Any, worksheet: Any, address: Any) -> str:
        return f"{self.worksheet(workbook_id, worksheet)}/range(address={odata_string(address)})"

    def used_range(self, workbook_id: Any, worksheet: Any) -> str:
        return f"{self.worksheet(workbook_id, worksheet)}/usedRange(valuesOnly=true)"

    def table(self, workbook_id: Any, table: Any) -> str:
        return f"{self.workbook(workbook_id)}/tables/{segment(table)}"


def resolve_graph_context(
    credentials: Mapping[str, Any], tool: Any = None, site_id: Any = None, drive_user: Any = None
) -> GraphContext:
    """
    Turn the runtime credentials, plus the tool's optional SharePoint Site ID and Drive Owner,
    into a token and the drive the workbook tools work in.

    ``tool`` is the calling Tool; per-user sign-in needs its user ID and plugin storage.
    When that user has not signed in yet, the GraphAuthError message is the sign-in link.
    """
    site_id = setting_value(site_id)
    drive_user = setting_value(drive_user)

    if is_per_user(credentials) or is_service_principal(credentials):
        _, graph_host = cloud_hosts(credentials.get("cloud"))
        api_base = f"{graph_host}/v1.0"
        if is_per_user(credentials):
            if drive_user:
                raise GraphAuthError(
                    "The Drive Owner setting only works with a Service Principal credential. "
                    "With per-user sign-in the tools use the calling user's own OneDrive (or the given site)."
                )
            if tool is None:
                raise GraphAuthError("Per-user sign-in is not available here.")
            token = user_access_token(credentials, tool)
            owner_drive = f"{api_base}/me/drive"
        else:
            token = acquire_app_token(
                credentials.get("tenant_id", ""),
                credentials.get("client_id", ""),
                credentials.get("client_secret", ""),
                credentials.get("cloud"),
            )
            owner = drive_user or (credentials.get("drive_user") or "").strip()
            if not owner and not site_id:
                raise GraphAuthError(
                    "A Service Principal has no signed-in user. Give the workbook's location: a SharePoint Site ID, "
                    "or a Drive Owner (on the credential or the tool) such as alice@contoso.com."
                )
            owner_drive = f"{api_base}/users/{quote(owner, safe='@.')}/drive" if owner else ""
        drive_base = f"{api_base}/sites/{site_segment(site_id)}/drive" if site_id else owner_drive
        return GraphContext(token, api_base, drive_base)

    token = credentials.get("access_token")
    if not token:
        raise GraphAuthError("Access token is missing. Please authorize the plugin first.")
    if drive_user:
        raise GraphAuthError(
            "The Drive Owner setting only works with a Service Principal credential. "
            "With OAuth sign-in the tools use the signed-in user's own OneDrive (or the given site)."
        )
    # Credentials authorized before national-cloud support have no graph_base_url: they are global.
    graph_host = (credentials.get("graph_base_url") or CLOUDS[DEFAULT_CLOUD][1]).rstrip("/")
    if graph_host not in {host for _, host in CLOUDS.values()}:
        # Never send the bearer token to a host that is not a Microsoft Graph endpoint.
        raise GraphAuthError(f"Unsupported Microsoft Graph endpoint '{graph_host}'.")
    api_base = f"{graph_host}/v1.0"
    drive_base = f"{api_base}/sites/{site_segment(site_id)}/drive" if site_id else f"{api_base}/me/drive"
    return GraphContext(token, api_base, drive_base)


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


def graph_request(
    ctx: GraphContext,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
    timeout: int = 60,
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
        404: "Not found: check the workbook ID, the worksheet or table name, and the Site ID or Drive Owner.",
        409: "Conflict: a worksheet or table with that name may already exist, or the workbook is locked.",
        429: "Microsoft Graph is throttling requests; wait a moment and retry.",
    }.get(response.status_code, "")
    return f"Excel API error {response.status_code}: {detail}" + (f" {hint}" if hint else "")


def parse_rows(value: Any, name: str = "values") -> list[list[Any]]:
    """
    A 2D array of cell values from a tool parameter: JSON text or a list. A flat list is one row.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise GraphAuthError(f"{name} is required.")
        try:
            value = json.loads(text)
        except ValueError as e:
            raise GraphAuthError(f'{name} must be a JSON array, e.g. [["Name", "Score"], ["Kim", 90]].') from e
    if not isinstance(value, list) or not value:
        raise GraphAuthError(f'{name} must be a non-empty JSON array, e.g. [["Name", "Score"], ["Kim", 90]].')
    rows = value if isinstance(value[0], list) else [value]
    width = len(rows[0])
    if not width or any(not isinstance(row, list) or len(row) != width for row in rows):
        raise GraphAuthError(f"Every row in {name} must be a list with the same number of cells.")
    return rows


def require(tool_parameters: Mapping[str, Any], *names: str) -> list[str]:
    """The stripped values of required string parameters; raises naming the first missing one."""
    values = []
    for name in names:
        value = str(tool_parameters.get(name) or "").strip()
        if not value:
            raise GraphAuthError(f"{name} is required.")
        values.append(value)
    return values


def context_for(tool: Any, tool_parameters: Mapping[str, Any]) -> GraphContext:
    """The Graph context for a tool call: its credentials, Site ID and Drive Owner."""
    return resolve_graph_context(
        tool.runtime.credentials, tool, tool_parameters.get("site_id"), tool_parameters.get("drive_user")
    )


# A cell reference such as "B5" or "$B$5".
_CELL = re.compile(r"\$?([A-Za-z]+)\$?(\d+)")


def top_left(address: str) -> tuple[int, int]:
    """
    (column index, row number) of the first cell of an address such as "Sheet1!C5:D6" or "C5".
    Only the part after the last "!" is a cell reference: a sheet name like "Sheet1" is not.
    """
    ref = str(address or "").rsplit("!", 1)[-1].strip()
    match = _CELL.match(ref)
    return (column_index(match.group(1).upper()), int(match.group(2))) if match else (0, 1)


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def column_index(letters: str) -> int:
    """A -> 0, Z -> 25, AA -> 26."""
    number = 0
    for ch in letters:
        number = number * 26 + ord(ch) - 64
    return number - 1
