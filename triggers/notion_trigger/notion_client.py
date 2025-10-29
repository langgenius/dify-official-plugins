"""Thin Notion REST API client used by the trigger events to hydrate payloads."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

import requests

logger = logging.getLogger(__name__)


class NotionAPIError(RuntimeError):
    """Raised when a Notion API request fails."""


class NotionClient:
    """Minimal client wrapping the Notion REST API endpoints needed by the trigger."""

    BASE_URL = "https://api.notion.com/v1"
    DEFAULT_VERSION = "2025-09-03"
    RETRYABLE_STATUS = {429, 502, 503, 504}

    def __init__(
        self,
        integration_token: str,
        *,
        api_version: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        if not integration_token:
            raise ValueError("integration_token is required")

        self._token = integration_token
        self._session = session or requests.Session()
        self._timeout = timeout
        self._max_retries = max(1, max_retries)
        self._headers = {
            "Authorization": f"Bearer {integration_token}",
            "Notion-Version": api_version or self.DEFAULT_VERSION,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # Public fetch helpers
    # ------------------------------------------------------------------ #

    def fetch_page(self, page_id: str) -> Mapping[str, Any] | None:
        """Return the Page object metadata (properties only)."""
        return self._get(f"/pages/{page_id}")

    def fetch_database(self, database_id: str) -> Mapping[str, Any] | None:
        """Return the Database object including its data sources."""
        return self._get(f"/databases/{database_id}")

    def fetch_data_source(self, data_source_id: str) -> Mapping[str, Any] | None:
        """Return the Data Source schema metadata."""
        return self._get(f"/data_sources/{data_source_id}")

    def fetch_block(self, block_id: str) -> Mapping[str, Any] | None:
        """Return a single Block object."""
        return self._get(f"/blocks/{block_id}")

    def fetch_block_children(self, block_id: str, *, page_size: int | None = None) -> Mapping[str, Any] | None:
        """Return the immediate children blocks for the given block."""
        params: dict[str, Any] | None = None
        if page_size:
            params = {"page_size": page_size}
        return self._get(f"/blocks/{block_id}/children", params=params)

    def fetch_comment(
        self,
        comment_id: str,
        *,
        block_id: str | None = None,
        discussion_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        """
        Retrieve a comment. The API does not officially expose a direct lookup,
        so we attempt `/comments/{comment_id}` first (supported in newer API versions),
        falling back to listing comments by block or discussion and locating the match.
        """
        direct = self._get(f"/comments/{comment_id}")
        if direct:
            return direct

        search_targets: list[tuple[str, dict[str, Any]]] = []
        if block_id:
            search_targets.append(("/comments", {"block_id": block_id}))
        if discussion_id:
            search_targets.append(("/comments", {"discussion_id": discussion_id}))

        for path, params in search_targets:
            listing = self._get(path, params=params)
            if not listing:
                continue
            results = listing.get("results") if isinstance(listing, Mapping) else None
            if not results:
                continue
            for item in results:
                if isinstance(item, Mapping) and item.get("id") == comment_id:
                    return item

        return None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any] | None:
        return self._request("GET", path, params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any] | None:
        url = f"{self.BASE_URL}{path}"
        backoff = 0.5

        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    headers=self._headers,
                    params=params,
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                if attempt == self._max_retries:
                    raise NotionAPIError(f"Request to {url} failed: {exc}") from exc
                logger.debug("Notion request error (%s), retrying in %.1fs", exc, backoff)
                time.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code == 404:
                return None

            if response.status_code in self.RETRYABLE_STATUS and attempt < self._max_retries:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        backoff = float(retry_after)
                    except ValueError:
                        pass
                logger.debug(
                    "Notion response %s for %s, retrying in %.1fs (attempt %d/%d)",
                    response.status_code,
                    url,
                    backoff,
                    attempt,
                    self._max_retries,
                )
                time.sleep(backoff)
                backoff *= 2
                continue

            if response.ok:
                if response.status_code == 204:
                    return None
                try:
                    return response.json()
                except ValueError as exc:  # pragma: no cover - unexpected HTML/text responses
                    raise NotionAPIError(f"Invalid JSON response from {url}") from exc

            message = self._build_error_message(response)
            raise NotionAPIError(message)

        return None

    @staticmethod
    def _build_error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
            detail = payload.get("message") or payload
        except ValueError:
            detail = response.text
        return f"Notion API request failed ({response.status_code}): {detail}"
