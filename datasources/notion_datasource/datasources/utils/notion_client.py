"""
Notion API Client for Dify plugins
This module provides a unified interface for interacting with the Notion API
"""

import os
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from dify_plugin.entities.datasource import OnlineDocumentPage

__TIMEOUT_SECONDS__ = 60 * 10
_DEFAULT_PARENT_RESOLVE_WORKERS = 8
_MAX_PARENT_RESOLVE_WORKERS = 32


class NotionClient:
    """
    A client for interacting with the Notion API.
    Abstracts the API calls and provides a unified interface for all Notion operations.
    """

    _API_BASE_URL = "https://api.notion.com/v1"
    _API_VERSION = "2022-06-28"  # Using a stable API version_API_VERSION = "2022-06-28"
    _AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
    _TOKEN_URL = "https://api.notion.com/v1/oauth/token"
    _NOTION_PAGE_SEARCH = "https://api.notion.com/v1/search"
    _NOTION_BLOCK_SEARCH = "https://api.notion.com/v1/blocks"
    _NOTION_BOT_USER = "https://api.notion.com/v1/users/me"

    def __init__(self, integration_token: str):
        """
        Initialize the Notion client with an integration token.

        Args:
            integration_token: The Notion integration token for authentication
        """
        self.integration_token = integration_token
        self.headers = {
            "Authorization": f"Bearer {integration_token}",
            "Notion-Version": self._API_VERSION,
            "Content-Type": "application/json",
        }
        # Memoize parent_id lookups so the threaded resolution in
        # get_authorized_pages doesn't re-fetch the same ancestor block twice.
        # `_parent_inflight` tracks lookups currently being resolved so that
        # concurrent workers asking for the same block coalesce onto a single
        # HTTP request instead of all racing past the cache miss.
        self._parent_cache: dict[str, str] = {}
        self._parent_inflight: dict[str, threading.Event] = {}
        self._parent_cache_lock = threading.Lock()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
        allow_status: Iterable[int] = (),
    ) -> dict[str, Any] | None:
        """
        Make an API request to Notion with retry logic for rate limits.

        Args:
            method: HTTP method (get, post, patch, etc.)
            endpoint: API endpoint (relative to base URL)
            params: URL parameters for GET requests
            json_data: JSON data for POST/PATCH requests
            max_retries: Maximum number of retries for rate limiting
            allow_status: HTTP status codes that should resolve to None
                instead of raising (e.g. {404} for optional resources).

        Returns:
            Response data as dictionary, or None if the response status was in allow_status.
        """
        url = f"{self._API_BASE_URL}{endpoint}"
        retries = 0
        allow_status_set = set(allow_status)

        while retries <= max_retries:
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                    json=json_data,
                    timeout=__TIMEOUT_SECONDS__,
                )

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    time.sleep(retry_after)
                    retries += 1
                    continue

                if response.status_code in allow_status_set:
                    return None

                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                # Format error based on Notion's error response structure
                if hasattr(e, "response") and e.response is not None:
                    try:
                        error_json = e.response.json()
                        error_message = error_json.get("message", str(e))
                        error_code = error_json.get("code", "unknown_error")
                        raise requests.exceptions.HTTPError(
                            f"Notion API Error: {error_code} - {error_message}",
                            response=e.response,
                        )
                    except ValueError:
                        # If not JSON response
                        pass
                raise

            except requests.exceptions.RequestException:
                if retries >= max_retries:
                    raise
                retries += 1
                time.sleep(1)

        # This should never happen, but just in case
        raise Exception("Maximum retries exceeded")

    def search(
        self,
        query: str,
        page_size: int = 10,
        start_cursor: str | None = None,
        filter_obj: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Search for pages and databases in a Notion workspace.

        Args:
            query: The search query string
            page_size: Maximum number of results to return (max 100)
            start_cursor: Cursor for pagination
            filter_obj: Filter object to restrict search to specific object types
            sort: Sort object to control the order of search results

        Returns:
            Dictionary containing search results
        """
        payload = {
            "query": query,
            "page_size": min(page_size, 100),  # Ensure page_size doesn't exceed API limit
        }

        if start_cursor:
            payload["start_cursor"] = start_cursor

        if filter_obj:
            payload["filter"] = filter_obj

        if sort:
            payload["sort"] = sort

        return self._make_request("post", "/search", json_data=payload)

    def query_database(
        self,
        database_id: str,
        filter_obj: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 10,
        start_cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        Query a Notion database with optional filtering and sorting.

        Args:
            database_id: The ID of the database to query
            filter_obj: Optional filter object according to Notion API specs
            sorts: Optional sort specifications
            page_size: Maximum number of results to return (max 100)
            start_cursor: Cursor for pagination

        Returns:
            Dictionary containing database query results
        """
        # Clean database_id (remove dashes if present)
        database_id = database_id.replace("-", "")

        payload: dict[str, Any] = {
            "page_size": min(page_size, 100)  # Ensure page_size doesn't exceed API limit
        }

        if filter_obj:
            payload["filter"] = filter_obj

        if sorts:
            payload["sorts"] = sorts

        if start_cursor:
            payload["start_cursor"] = start_cursor

        return self._make_request("post", f"/databases/{database_id}/query", json_data=payload)

    def retrieve_block_children(
        self, block_id: str, page_size: int = 100, start_cursor: str | None = None
    ) -> dict[str, Any]:
        """
        Retrieve the children blocks of a block.

        Args:
            block_id: The ID of the block to retrieve children from
            page_size: Maximum number of results to return (max 100)
            start_cursor: Cursor for pagination

        Returns:
            Dictionary containing the block children
        """
        block_id = block_id.replace("-", "")

        params: dict[str, Any] = {
            "page_size": min(page_size, 100)  # Ensure page_size doesn't exceed API limit
        }

        if start_cursor:
            params["start_cursor"] = start_cursor

        return self._make_request("get", f"/blocks/{block_id}/children", params=params)

    def append_block_children(self, block_id: str, children: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Append children blocks to a block.

        Args:
            block_id: The ID of the block to append children to
            children: List of block contents to append

        Returns:
            Dictionary containing the updated block information
        """
        block_id = block_id.replace("-", "")

        payload = {"children": children}

        return self._make_request("patch", f"/blocks/{block_id}/children", json_data=payload)

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        """
        Retrieve a page by its ID.

        Args:
            page_id: The ID of the page to retrieve

        Returns:
            Dictionary containing the page information
        """
        page_id = page_id.replace("-", "")
        return self._make_request("get", f"/pages/{page_id}")

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        """
        Retrieve a database by its ID.

        Args:
            database_id: The ID of the database to retrieve

        Returns:
            Dictionary containing the database information
        """
        database_id = database_id.replace("-", "")
        return self._make_request("get", f"/databases/{database_id}")

    def create_property_filter(
        self, property_name: str, property_type: str, condition: str, value: Any
    ) -> dict[str, Any]:
        """
        Create a property filter for database queries.

        Args:
            property_name: Name of the property to filter on
            property_type: Type of the property (text, number, checkbox, etc.)
            condition: Filter condition (equals, contains, greater_than, etc.)
            value: Value to filter by

        Returns:
            Filter object for use with query_database
        """
        return {"property": property_name, property_type: {condition: value}}

    def create_simple_text_filter(
        self, property_name: str, filter_value: str, condition: str = "equals"
    ) -> dict[str, Any]:
        """
        Create a simple text filter for database queries.

        Args:
            property_name: Name of the property to filter on
            filter_value: Value to filter by
            condition: Filter condition (equals, contains, starts_with, ends_with)

        Returns:
            Filter object for use with query_database
        """
        return self.create_property_filter(property_name, "rich_text", condition, filter_value)

    def format_page_url(self, page_id: str) -> str:
        """
        Format a page ID into a Notion URL.

        Args:
            page_id: The page ID

        Returns:
            Formatted Notion URL for the page
        """
        # Make sure the page_id is properly formatted (with hyphens)
        clean_id = page_id.replace("-", "")
        formatted_id = f"{clean_id[0:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}"
        return f"https://notion.so/{formatted_id}"

    def extract_plain_text(self, rich_text_array: list[dict[str, Any]]) -> str:
        """
        Extract plain text from a rich text array.

        Args:
            rich_text_array: Array of rich text objects

        Returns:
            Plain text string
        """
        if not rich_text_array:
            return ""

        return "".join([text.get("plain_text", "") for text in rich_text_array])

    def create_rich_text(self, content: str, annotations: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Create a rich text array with the specified content and optional annotations.

        Args:
            content: The text content
            annotations: Optional text annotations (bold, italic, etc.)

        Returns:
            Rich text array for use with Notion API
        """
        rich_text = {"type": "text", "text": {"content": content}}

        if annotations:
            rich_text["annotations"] = annotations

        return [rich_text]

    def create_paragraph_block(self, text_content: str) -> dict[str, Any]:
        """
        Create a paragraph block with the specified text content.

        Args:
            text_content: The text content of the paragraph

        Returns:
            Paragraph block for use with Notion API
        """
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": self.create_rich_text(text_content)},
        }

    def create_heading_block(self, text_content: str, level: int = 1) -> dict[str, Any]:
        """
        Create a heading block with the specified text content and level.

        Args:
            text_content: The text content of the heading
            level: Heading level (1, 2, or 3)

        Returns:
            Heading block for use with Notion API
        """
        if level not in [1, 2, 3]:
            raise ValueError("Heading level must be 1, 2, or 3")

        heading_type = f"heading_{level}"

        return {
            "object": "block",
            "type": heading_type,
            heading_type: {"rich_text": self.create_rich_text(text_content)},
        }

    def create_bulleted_list_block(self, text_content: str) -> dict[str, Any]:
        """
        Create a bulleted list item block with the specified text content.

        Args:
            text_content: The text content of the list item

        Returns:
            Bulleted list item block for use with Notion API
        """
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": self.create_rich_text(text_content)},
        }

    def create_numbered_list_block(self, text_content: str) -> dict[str, Any]:
        """
        Create a numbered list item block with the specified text content.

        Args:
            text_content: The text content of the list item

        Returns:
            Numbered list item block for use with Notion API
        """
        return {
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": self.create_rich_text(text_content)},
        }

    def retrieve_comments(self, block_id: str, page_size: int = 100, start_cursor: str | None = None) -> dict[str, Any]:
        """
        Retrieve comments from a block or page.

        Args:
            block_id: The ID of the block or page
            page_size: Maximum number of comments to retrieve
            start_cursor: Pagination cursor

        Returns:
            Comments data including results array
        """
        endpoint = "/comments"
        params = {"block_id": block_id, "page_size": page_size}

        if start_cursor:
            params["start_cursor"] = start_cursor

        return self._make_request("GET", endpoint, params=params)

    def format_rich_text(self, content: str) -> list[dict[str, Any]]:
        """
        Format plain text into rich text array for Notion API.
        Wrapper around create_rich_text for simplified usage.

        Args:
            content: Plain text content

        Returns:
            Rich text array for Notion API
        """
        return self.create_rich_text(content)

    def get_authorized_pages(self) -> list[OnlineDocumentPage]:
        items = self._search_all()
        worker_count = self._resolve_worker_count()

        pages: list[OnlineDocumentPage] = []
        if worker_count <= 1:
            for item in items:
                entry = self._build_page_entry(item)
                if entry is not None:
                    pages.append(entry)
            return pages

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for entry in executor.map(self._build_page_entry, items):
                if entry is not None:
                    pages.append(entry)
        return pages

    def _search_all(self) -> list[dict[str, Any]]:
        """Fetch every page and database shared with the integration in one pass.

        Notion's /v1/search returns both pages and databases when no object filter
        is supplied, so combining the previous two filtered loops halves the number
        of search round-trips required to enumerate the workspace.
        """
        results: list[dict[str, Any]] = []
        next_cursor: str | None = None
        has_more = True
        while has_more:
            payload: dict[str, Any] = {}
            if next_cursor:
                payload["start_cursor"] = next_cursor
            data = self._make_request("post", "/search", json_data=payload) or {}
            results.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            next_cursor = data.get("next_cursor")
        return results

    def _build_page_entry(self, item: dict[str, Any]) -> OnlineDocumentPage | None:
        obj = item.get("object")
        if obj == "page":
            page_name = "Untitled"
            for key in item.get("properties", {}):
                prop = item["properties"][key]
                if "title" in prop and prop["title"]:
                    title_list = prop["title"]
                    if len(title_list) > 0 and "plain_text" in title_list[0]:
                        page_name = title_list[0]["plain_text"]
            page_type = "page"
        elif obj == "database":
            title = item.get("title", [])
            page_name = title[0]["plain_text"] if len(title) > 0 else "Untitled"
            page_type = "database"
        else:
            return None

        parent = item.get("parent", {})
        parent_type = parent.get("type")
        try:
            if parent_type == "block_id":
                parent_id = self._resolve_block_parent_page_id(parent[parent_type])
            elif parent_type == "workspace":
                parent_id = "root"
            elif parent_type and parent_type in parent:
                parent_id = parent[parent_type]
            else:
                parent_id = "root"
        except (ValueError, requests.exceptions.RequestException):
            # One unresolvable item (HTTP error, malformed parent, etc.) must not
            # abort the whole enumeration — preserve the original "skip and
            # continue" behavior established by PR #2891.
            return None

        return OnlineDocumentPage(
            page_id=item["id"],
            page_name=page_name,
            page_icon=None,
            parent_id=parent_id,
            type=page_type,
            last_edited_time=item["last_edited_time"],
        )

    @staticmethod
    def _resolve_worker_count() -> int:
        raw = os.environ.get("NOTION_PARENT_RESOLVE_WORKERS")
        if not raw:
            return _DEFAULT_PARENT_RESOLVE_WORKERS
        try:
            value = int(raw)
        except ValueError:
            return _DEFAULT_PARENT_RESOLVE_WORKERS
        return max(1, min(value, _MAX_PARENT_RESOLVE_WORKERS))

    def notion_page_search(self, access_token: str):
        return self._search_filtered("page")

    def notion_database_search(self, access_token: str):
        return self._search_filtered("database")

    def _search_filtered(self, object_type: str) -> list[dict[str, Any]]:
        """Fetch only pages or only databases using the API-side object filter.

        Used by the public ``notion_page_search`` / ``notion_database_search``
        wrappers when callers ask for just one type. ``get_authorized_pages``
        deliberately uses ``_search_all`` instead to collapse both kinds into a
        single pass.
        """
        results: list[dict[str, Any]] = []
        next_cursor: str | None = None
        has_more = True
        while has_more:
            payload: dict[str, Any] = {
                "filter": {"value": object_type, "property": "object"},
            }
            if next_cursor:
                payload["start_cursor"] = next_cursor
            data = self._make_request("post", "/search", json_data=payload) or {}
            results.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            next_cursor = data.get("next_cursor")
        return results

    def notion_block_parent_page_id(self, access_token: str, block_id: str):
        return self._resolve_block_parent_page_id(block_id)

    def _resolve_block_parent_page_id(self, block_id: str) -> str:
        clean_id = block_id.replace("-", "")

        # Coordinate cache and in-flight lookups under the same lock so two
        # workers can never both miss the cache for the same block and race to
        # fetch it — under Notion's ~3 req/s limit those redundant requests
        # would just amplify 429 backoff.
        while True:
            with self._parent_cache_lock:
                cached = self._parent_cache.get(clean_id)
                if cached is not None:
                    return cached
                event = self._parent_inflight.get(clean_id)
                if event is None:
                    # This thread is now responsible for fetching this id;
                    # other threads asking for the same id will wait on `event`.
                    event = threading.Event()
                    self._parent_inflight[clean_id] = event
                    break
            # Another worker is already fetching; wait for it to finish, then
            # re-check the cache on the next iteration.
            event.wait()

        try:
            data = self._make_request("get", f"/blocks/{clean_id}", allow_status=(404,))
            if data is None:
                result = "root"
            else:
                parent = data.get("parent", {})
                parent_type = parent.get("type")
                if parent_type == "block_id":
                    result = self._resolve_block_parent_page_id(parent[parent_type])
                elif parent_type == "workspace":
                    result = "root"
                elif parent_type and parent_type in parent:
                    result = parent[parent_type]
                else:
                    result = "root"
        except Exception:
            # Release waiters so they don't block forever; they will re-enter
            # the lock above, see no cache entry, and retry on their own.
            with self._parent_cache_lock:
                self._parent_inflight.pop(clean_id, None)
            event.set()
            raise

        with self._parent_cache_lock:
            self._parent_cache[clean_id] = result
            self._parent_inflight.pop(clean_id, None)
        event.set()
        return result
