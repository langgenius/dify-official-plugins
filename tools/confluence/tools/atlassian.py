"""
Atlassian OAuth 2.0 (3LO) helpers shared by the OAuth credential and per-user sign-in.

An Atlassian access token is not tied to one site: after sign-in the token is exchanged
for the list of sites the user granted (``accessible-resources``) and the Confluence REST API
is called through ``https://api.atlassian.com/ex/confluence/<cloud id>/wiki``. When the user
can reach several sites, the configured Site URL picks one; otherwise the first Confluence
site is used.
"""

import urllib.parse
from typing import Any, Mapping

import requests

AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
TOKEN_URL = "https://auth.atlassian.com/oauth/token"
API_HOST = "https://api.atlassian.com"
RESOURCES_URL = f"{API_HOST}/oauth/token/accessible-resources"

# Granular Confluence scopes: they cover both the v2 API (pages, spaces, comments, labels,
# attachments) and the v1 endpoints still needed (CQL search, label and attachment writes).
# Every scope here except offline_access must also be added to the app in the Atlassian developer console.
DEFAULT_SCOPE = (
    "read:page:confluence write:page:confluence delete:page:confluence read:space:confluence "
    "read:hierarchical-content:confluence read:content-details:confluence "
    "read:comment:confluence write:comment:confluence delete:comment:confluence "
    "read:label:confluence write:label:confluence "
    "read:attachment:confluence write:attachment:confluence delete:attachment:confluence "
    "read:user:confluence offline_access"
)


class AtlassianAuthError(Exception):
    """Atlassian refused a request or could not be reached; the message is shown to the user."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def scope(credentials: Mapping[str, Any]) -> str:
    """The configured scopes (comma or space separated), always with offline_access so tokens can refresh."""
    items = (credentials.get("scopes") or "").replace(",", " ").split() or DEFAULT_SCOPE.split()
    if "offline_access" not in items:
        items.append("offline_access")
    return " ".join(dict.fromkeys(items))


def authorization_url(client_id: str, redirect_uri: str, state: str, scopes: str) -> str:
    return f"{AUTHORIZE_URL}?" + urllib.parse.urlencode(
        {
            "audience": "api.atlassian.com",
            "client_id": client_id,
            "scope": scopes,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
    )


def token_request(data: Mapping[str, str]) -> dict[str, Any]:
    """POST to the token endpoint (Atlassian takes JSON); errors raise AtlassianAuthError with the status."""
    try:
        response = requests.post(TOKEN_URL, json=dict(data), headers={"Accept": "application/json"}, timeout=30)
    except requests.exceptions.RequestException as e:
        raise AtlassianAuthError(f"Could not reach Atlassian: {e}") from e
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code != 200 or not payload.get("access_token"):
        detail = payload.get("error_description") or payload.get("error") or response.text[:300]
        raise AtlassianAuthError(f"Atlassian sign-in failed ({response.status_code}): {detail}", response.status_code)
    return payload


def normalize_site_url(url: str | None) -> str:
    """'acme.atlassian.net', 'https://acme.atlassian.net/wiki/...' -> 'https://acme.atlassian.net'."""
    value = (url or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    parsed = urllib.parse.urlparse(value)
    return f"https://{(parsed.hostname or '').lower()}"


def pick_site(resources: list[Mapping[str, Any]], site_url: str | None = None) -> dict[str, str]:
    """The site to use: the one matching ``site_url``, else the first one that grants Confluence scopes."""
    if not resources:
        raise AtlassianAuthError(
            "The Atlassian account did not grant access to any site. Sign in again and pick a Confluence site on the consent screen."
        )
    wanted = normalize_site_url(site_url)
    if wanted:
        for resource in resources:
            if normalize_site_url(resource.get("url")) == wanted:
                return _site(resource)
        available = ", ".join(str(r.get("url", "")) for r in resources)
        raise AtlassianAuthError(f"The account has no access to {wanted}. Sites it granted: {available}.")
    confluence = [r for r in resources if any("confluence" in str(s) for s in r.get("scopes") or [])]
    return _site((confluence or list(resources))[0])


def _site(resource: Mapping[str, Any]) -> dict[str, str]:
    return {"cloud_id": str(resource.get("id", "")), "site_url": str(resource.get("url", "")).rstrip("/")}


def find_site(access_token: str, site_url: str | None = None) -> dict[str, str]:
    """Cloud ID and URL of the Confluence site this token is for."""
    try:
        response = requests.get(
            RESOURCES_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        raise AtlassianAuthError(f"Could not reach Atlassian: {e}") from e
    if response.status_code != 200:
        raise AtlassianAuthError(
            f"Could not list the Atlassian sites for this sign-in ({response.status_code}).", response.status_code
        )
    return pick_site(response.json(), site_url)


def account_name(access_token: str, cloud_id: str) -> str | None:
    """
    The signed-in account's email (or name), so the user can spot a wrong account; best effort.
    Read from Confluence's current user (scope read:user:confluence), so the app needs no User identity API scope.
    """
    try:
        response = requests.get(
            f"{API_HOST}/ex/confluence/{urllib.parse.quote(cloud_id, safe='')}/wiki/rest/api/user/current",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=15,
        )
        if response.status_code == 200:
            me = response.json()
            return me.get("email") or me.get("displayName") or me.get("publicName")
    except (requests.exceptions.RequestException, ValueError):
        pass
    return None
