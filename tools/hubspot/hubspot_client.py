"""Shared HubSpot v3 REST client for the plugin tools.

Uses form/JSON requests against api.hubapi.com with a private-app access token.
The `search` helper exposes HubSpot's Search API (filter + sort + query), which
is what every "list / search" tool should use so large result sets can be
filtered and ordered.
"""
from __future__ import annotations

from typing import Any, Optional

import requests

HUBSPOT_API = "https://api.hubapi.com"

# HubSpot CRM Search operators, offered to users on filterable tools.
SEARCH_OPERATORS = [
    "EQ", "NEQ", "LT", "LTE", "GT", "GTE", "BETWEEN", "IN", "NOT_IN",
    "HAS_PROPERTY", "NOT_HAS_PROPERTY", "CONTAINS_TOKEN", "NOT_CONTAINS_TOKEN",
]


class HubSpotError(Exception):
    """Raised when the HubSpot API returns an error or is unreachable."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status = status


class HubSpotClient:
    def __init__(self, access_token: str, timeout: float = 30.0):
        access_token = (access_token or "").strip()
        if not access_token:
            raise HubSpotError("A HubSpot private-app access token is required.")
        self.timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        url = f"{HUBSPOT_API}{path}"
        try:
            resp = requests.request(
                method, url, headers=self._headers, timeout=self.timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise HubSpotError(f"HTTP error calling HubSpot: {exc}")
        if resp.status_code == 401:
            raise HubSpotError("Unauthorized - check the access token and its scopes.", 401)
        if not resp.ok:
            raise HubSpotError(f"HubSpot API error {resp.status_code}: {resp.text}", resp.status_code)
        return resp.json() if resp.text else {}

    # --- CRM object CRUD (object = contacts | companies | deals | tickets | notes | tasks | ...) ---
    def create(self, obj: str, properties: dict[str, Any], associations: Optional[list] = None) -> dict[str, Any]:
        body: dict[str, Any] = {"properties": properties}
        if associations:
            body["associations"] = associations
        return self._request("POST", f"/crm/v3/objects/{obj}", json=body)

    def update(self, obj: str, object_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/crm/v3/objects/{obj}/{object_id}", json={"properties": properties})

    def delete(self, obj: str, object_id: str) -> dict[str, Any]:
        self._request("DELETE", f"/crm/v3/objects/{obj}/{object_id}")
        return {"id": object_id, "deleted": True}

    def get(self, obj: str, object_id: str, properties: Optional[list[str]] = None,
            associations: Optional[list[str]] = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if properties:
            params["properties"] = ",".join(properties)
        if associations:
            params["associations"] = ",".join(associations)
        return self._request("GET", f"/crm/v3/objects/{obj}/{object_id}", params=params)

    def search(
        self,
        obj: str,
        *,
        query: Optional[str] = None,
        filter_property: Optional[str] = None,
        filter_operator: str = "EQ",
        filter_value: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_direction: str = "DESCENDING",
        properties: Optional[list[str]] = None,
        limit: int = 20,
        after: Optional[str] = None,
    ) -> dict[str, Any]:
        """Search a CRM object with optional full-text query, a single filter, and sort."""
        body: dict[str, Any] = {"limit": max(1, min(int(limit or 20), 100))}
        if query:
            body["query"] = query
        if properties:
            body["properties"] = properties
        if after:
            body["after"] = after
        if sort_by:
            direction = (sort_direction or "DESCENDING").upper()
            if direction not in ("ASCENDING", "DESCENDING"):
                direction = "DESCENDING"
            body["sorts"] = [{"propertyName": sort_by, "direction": direction}]
        if filter_property:
            op = (filter_operator or "EQ").upper()
            f: dict[str, Any] = {"propertyName": filter_property, "operator": op}
            if op not in ("HAS_PROPERTY", "NOT_HAS_PROPERTY") and filter_value is not None:
                f["value"] = filter_value
            body["filterGroups"] = [{"filters": [f]}]
        return self._request("POST", f"/crm/v3/objects/{obj}/search", json=body)

    # --- Contact list membership (v3 lists) ---
    def add_to_list(self, list_id: str, record_ids: list[str]) -> dict[str, Any]:
        return self._request("PUT", f"/crm/v3/lists/{list_id}/memberships/add", json=record_ids)

    def remove_from_list(self, list_id: str, record_ids: list[str]) -> dict[str, Any]:
        return self._request("PUT", f"/crm/v3/lists/{list_id}/memberships/remove", json=record_ids)

    # --- Forms ---
    def get_form(self, form_id: str) -> dict[str, Any]:
        return self._request("GET", f"/marketing/v3/forms/{form_id}")
