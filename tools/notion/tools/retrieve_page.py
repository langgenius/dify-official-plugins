import mimetypes
import time
from collections.abc import Generator
from typing import Any, Dict, List
from urllib.parse import urlparse
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient

DEFAULT_MAX_DEPTH = 5
DEFAULT_MAX_API_CALLS = 500
DEFAULT_MAX_IMAGES = 20
DEFAULT_IMAGE_DOWNLOAD_TIMEOUT = 30
DEFAULT_IMAGE_MIME_TYPE = "image/png"
DEFAULT_MAX_IMAGE_SIZE = 15 * 1024 * 1024  # 15MB per image
DEFAULT_MAX_CUMULATIVE_IMAGE_SIZE = 100 * 1024 * 1024  # 100MB per retrieval
IMAGE_DOWNLOAD_CHUNK_SIZE = 8192

# Block types whose "children" are separate pages/databases, not nested content
# of the current page. Recursing into them would silently pull in arbitrary
# linked pages, so we skip them. Users can call retrieve_page on those IDs
# explicitly if needed.
NON_CONTENT_CONTAINER_TYPES = frozenset({"child_page", "child_database"})


class _FetchBudget:
    """Tracks API calls and blocks fetched for a single retrieve_page invocation."""

    def __init__(self, max_api_calls: int):
        self.max_api_calls = max_api_calls
        self.api_calls_made = 0
        self.total_blocks_fetched = 0
        self.truncated = False

    def can_spend(self) -> bool:
        return self.api_calls_made < self.max_api_calls

    def spend(self) -> None:
        self.api_calls_made += 1

    def mark_truncated(self) -> None:
        self.truncated = True


class RetrievePageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        page_id = tool_parameters.get("page_id", "")
        include_content = tool_parameters.get("include_content", True)
        max_depth = _coerce_positive_int(
            tool_parameters.get("max_depth"), DEFAULT_MAX_DEPTH
        )
        max_api_calls = _coerce_positive_int(
            tool_parameters.get("max_api_calls"), DEFAULT_MAX_API_CALLS
        )
        # max_api_calls must be at least 1 so the initial page fetch can run.
        if max_api_calls < 1:
            max_api_calls = 1
        max_images = _coerce_positive_int(
            tool_parameters.get("max_images"), DEFAULT_MAX_IMAGES
        )

        # Validate parameters
        if not page_id:
            yield self.create_text_message("Page ID is required.")
            return

        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return

            # Initialize the Notion client
            client = NotionClient(integration_token)

            # Retrieve the page
            try:
                started_at = time.monotonic()
                page_data = client.retrieve_page(page_id)

                # Format the page data
                formatted_page = self._format_page_data(client, page_data)

                budget = _FetchBudget(max_api_calls=max_api_calls)
                collected_images: List[Dict[str, Any]] = []
                # Retrieve page content if requested
                if include_content:
                    try:
                        all_blocks = self._fetch_all_children(client, page_id, budget)
                        formatted_page["content"] = self._format_blocks(
                            client, all_blocks, budget, collected_images,
                            depth=0, max_depth=max_depth, max_images=max_images,
                        )
                    except requests.HTTPError as e:
                        # If we can't get the content, just return the page data
                        formatted_page["content_error"] = str(e)

                # Format URL
                formatted_page["url"] = client.format_page_url(page_id)

                # Telemetry: observable cost of this retrieval.
                formatted_page["api_calls_made"] = budget.api_calls_made
                formatted_page["total_blocks_fetched"] = budget.total_blocks_fetched
                formatted_page["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
                if budget.truncated:
                    formatted_page["fetch_truncated"] = True
                    formatted_page["fetch_truncated_reason"] = (
                        f"max_api_calls={max_api_calls} exceeded; increase the limit or raise max_depth with care."
                    )
                if len(collected_images) > max_images:
                    formatted_page["images_skipped"] = len(collected_images) - max_images
                    collected_images = collected_images[:max_images]

                # Return results
                title = formatted_page.get("title", "Untitled")
                yield self.create_text_message(f"Retrieved page: {title}")
                yield self.create_json_message(formatted_page)

                # Download image blocks so they surface in the tool's `files`
                # output. Notion image URLs are short-lived (~1 hour) S3
                # signed URLs, so we must fetch them now rather than later.
                images_downloaded = 0
                images_failed = 0
                total_downloaded_bytes = 0
                for image in collected_images:
                    if total_downloaded_bytes >= DEFAULT_MAX_CUMULATIVE_IMAGE_SIZE:
                        images_failed += 1
                        continue
                    try:
                        blob, mime_type, filename = _download_image(
                            image["url"],
                            image["block_id"],
                            max_bytes=min(
                                DEFAULT_MAX_IMAGE_SIZE,
                                DEFAULT_MAX_CUMULATIVE_IMAGE_SIZE - total_downloaded_bytes,
                            ),
                        )
                        yield self.create_blob_message(
                            blob=blob,
                            meta={"mime_type": mime_type, "filename": filename},
                        )
                        images_downloaded += 1
                        total_downloaded_bytes += len(blob)
                    except Exception:
                        images_failed += 1
                if images_downloaded or images_failed:
                    yield self.create_text_message(
                        f"Downloaded {images_downloaded} image(s)"
                        + (f", {images_failed} failed" if images_failed else "")
                    )

            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Page not found or you don't have access to it: {page_id}")
                else:
                    yield self.create_text_message(f"Error retrieving page: {e}")
                return

        except Exception as e:
            yield self.create_text_message(f"Error retrieving Notion page: {str(e)}")
            return

    def _format_page_data(self, client: NotionClient, page_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format the page data for the response."""
        result = {
            "id": page_data.get("id", ""),
            "created_time": page_data.get("created_time", ""),
            "last_edited_time": page_data.get("last_edited_time", ""),
            "archived": page_data.get("archived", False),
        }

        # Extract properties
        properties = page_data.get("properties", {})
        formatted_properties = {}

        title = "Untitled"
        for prop_name, prop_data in properties.items():
            prop_type = prop_data.get("type")

            # Extract value based on property type
            if prop_type == "title":
                title_content = prop_data.get("title", [])
                value = client.extract_plain_text(title_content)
                if value:
                    title = value  # Save title for the result
            elif prop_type == "rich_text":
                text_content = prop_data.get("rich_text", [])
                value = client.extract_plain_text(text_content)
            elif prop_type == "number":
                value = prop_data.get("number")
            elif prop_type == "select":
                select_data = prop_data.get("select", {})
                value = select_data.get("name") if select_data else None
            elif prop_type == "multi_select":
                multi_select = prop_data.get("multi_select", [])
                value = [item.get("name") for item in multi_select] if multi_select else []
            elif prop_type == "date":
                date_data = prop_data.get("date", {})
                start = date_data.get("start") if date_data else None
                end = date_data.get("end") if date_data else None
                value = {"start": start, "end": end} if start else None
            elif prop_type == "checkbox":
                value = prop_data.get("checkbox")
            elif prop_type == "url":
                value = prop_data.get("url")
            elif prop_type == "email":
                value = prop_data.get("email")
            elif prop_type == "phone_number":
                value = prop_data.get("phone_number")
            else:
                # For other property types, just note the type
                value = f"<{prop_type}>"

            formatted_properties[prop_name] = value

        result["title"] = title
        result["properties"] = formatted_properties
        return result

    def _fetch_all_children(
        self,
        client: NotionClient,
        block_id: str,
        budget: "_FetchBudget",
    ) -> List[Dict[str, Any]]:
        """Fetch every child block of the given block, paginating until exhausted or the budget is reached."""
        blocks: List[Dict[str, Any]] = []
        start_cursor = None
        while True:
            if not budget.can_spend():
                budget.mark_truncated()
                break
            budget.spend()
            response = client.retrieve_block_children(block_id, start_cursor=start_cursor)
            page_results = response.get("results", [])
            blocks.extend(page_results)
            budget.total_blocks_fetched += len(page_results)
            if not response.get("has_more"):
                break
            start_cursor = response.get("next_cursor")
            if not start_cursor:
                break
        return blocks

    def _format_blocks(
        self,
        client: NotionClient,
        blocks: List[Dict[str, Any]],
        budget: "_FetchBudget",
        collected_images: List[Dict[str, Any]],
        depth: int = 0,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_images: int = DEFAULT_MAX_IMAGES,
    ) -> List[Dict[str, Any]]:
        """Format block content for the response, recursing into nested children."""
        formatted_blocks = []

        for block in blocks:
            block_id = block.get("id", "")
            block_type = block.get("type", "")
            has_children = block.get("has_children", False)

            formatted_block = {
                "id": block_id,
                "type": block_type,
                "has_children": has_children
            }

            # Extract content based on block type
            if block_type == "paragraph":
                rich_text = block.get("paragraph", {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                formatted_block["text"] = text
            elif block_type in ["heading_1", "heading_2", "heading_3"]:
                rich_text = block.get(block_type, {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                formatted_block["text"] = text
            elif block_type == "bulleted_list_item":
                rich_text = block.get("bulleted_list_item", {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                formatted_block["text"] = text
            elif block_type == "numbered_list_item":
                rich_text = block.get("numbered_list_item", {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                formatted_block["text"] = text
            elif block_type == "to_do":
                rich_text = block.get("to_do", {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                checked = block.get("to_do", {}).get("checked", False)
                formatted_block["text"] = text
                formatted_block["checked"] = checked
            elif block_type == "toggle":
                rich_text = block.get("toggle", {}).get("rich_text", [])
                text = client.extract_plain_text(rich_text)
                formatted_block["text"] = text
            elif block_type == "quote":
                rich_text = block.get("quote", {}).get("rich_text", [])
                text = client.extract_plain_text(rich_text)
                formatted_block["text"] = text
            elif block_type == "callout":
                rich_text = block.get("callout", {}).get("rich_text", [])
                text = client.extract_plain_text(rich_text)
                formatted_block["text"] = text
            elif block_type == "code":
                code_block = block.get("code", {})
                rich_text = code_block.get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                language = code_block.get("language", "")
                formatted_block["text"] = text
                formatted_block["language"] = language
            elif block_type == "image":
                image_block = block.get("image", {})
                caption = image_block.get("caption", [])
                caption_text = "".join([rt.get("plain_text", "") for rt in caption])

                # Get image URL based on type
                image_type = image_block.get("type", "")
                if image_type == "external":
                    image_url = image_block.get("external", {}).get("url", "")
                elif image_type == "file":
                    image_url = image_block.get("file", {}).get("url", "")
                else:
                    image_url = ""

                formatted_block["caption"] = caption_text
                formatted_block["url"] = image_url

                if image_url:
                    collected_images.append({
                        "block_id": block_id,
                        "url": image_url,
                        "caption": caption_text,
                    })
            elif block_type == "table_row":
                cells = block.get("table_row", {}).get("cells", [])
                cell_texts = [client.extract_plain_text(cell) for cell in cells]
                formatted_block["cells"] = cell_texts
                formatted_block["text"] = " | ".join(cell_texts)
            elif block_type == "table":
                formatted_block["text"] = ""
            else:
                # For unsupported block types, just include the type
                formatted_block["text"] = f"<{block_type} block>"

            # Recurse into children when available, but skip linked sub-pages
            # and sub-databases (those are separately retrievable).
            if has_children and block_type not in NON_CONTENT_CONTAINER_TYPES:
                if depth >= max_depth:
                    formatted_block["children_truncated"] = True
                elif not budget.can_spend():
                    formatted_block["children_truncated"] = True
                    budget.mark_truncated()
                else:
                    try:
                        child_blocks = self._fetch_all_children(client, block_id, budget)
                        formatted_block["children"] = self._format_blocks(
                            client, child_blocks, budget, collected_images,
                            depth=depth + 1, max_depth=max_depth, max_images=max_images,
                        )
                    except requests.HTTPError as e:
                        # Record per-block failure but keep the rest of the page intact
                        formatted_block["children_error"] = str(e)

            if block_type == "table":
                children = formatted_block.get("children", [])
                row_cells = [
                    child["cells"]
                    for child in children
                    if child.get("type") == "table_row" and "cells" in child
                ]
                if row_cells:
                    headers = row_cells[0]
                    rows = row_cells[1:] if len(row_cells) > 1 else []
                    formatted_block["text"] = _generate_markdown_table(headers, rows)

            formatted_blocks.append(formatted_block)

        return formatted_blocks


def _escape_markdown_cell(cell: Any) -> str:
    if cell is None:
        return ""
    return str(cell).replace("|", "\\|").replace("\n", "<br>")


def _generate_markdown_table(headers: List[str], rows: List[List[str]]) -> str:
    """Build a markdown table from header and body rows."""
    if not headers:
        return ""
    escaped_headers = [_escape_markdown_cell(h) for h in headers]
    lines = [
        "| " + " | ".join(escaped_headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        escaped_row = [_escape_markdown_cell(cell) for cell in row]
        lines.append("| " + " | ".join(escaped_row) + " |")
    return "\n".join(lines)


def _coerce_positive_int(value: Any, default: int) -> int:
    """Best-effort int coercion; negatives clamp to 0 so callers can disable recursion."""
    try:
        coerced = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return max(coerced, 0)


def _download_image(url: str, block_id: str, max_bytes: int) -> tuple[bytes, str, str]:
    """Stream-download an image, aborting once it exceeds max_bytes so a single
    huge or malicious response can't exhaust the plugin's memory budget."""
    with requests.get(url, timeout=DEFAULT_IMAGE_DOWNLOAD_TIMEOUT, stream=True) as response:
        response.raise_for_status()

        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"Image at {url} exceeds the {max_bytes}-byte download limit")

        content = bytearray()
        for chunk in response.iter_content(chunk_size=IMAGE_DOWNLOAD_CHUNK_SIZE):
            content.extend(chunk)
            if len(content) > max_bytes:
                raise ValueError(f"Image at {url} exceeds the {max_bytes}-byte download limit")

        mime_type = _guess_image_mime_type(response, url)
        filename = _guess_image_filename(url, block_id, mime_type)
        return bytes(content), mime_type, filename


def _guess_image_mime_type(response: requests.Response, url: str) -> str:
    """Determine mime type from the response's Content-Type header, falling back
    to guessing from the URL's file extension when the header is missing, generic,
    or not an image type, then a hardcoded default."""
    content_type = response.headers.get("Content-Type", "")
    mime_type = content_type.split(";")[0].strip().lower()
    if mime_type and mime_type != "application/octet-stream" and mime_type.startswith("image/"):
        return mime_type
    guessed_type, _ = mimetypes.guess_type(urlparse(url).path)
    return guessed_type or DEFAULT_IMAGE_MIME_TYPE


def _guess_image_filename(url: str, block_id: str, mime_type: str) -> str:
    """Derive a filename from the URL path, falling back to the block ID with
    an extension guessed from the mime type."""
    path = urlparse(url).path
    filename = path.rstrip("/").split("/")[-1] if path else ""
    if filename:
        return filename
    extension = mimetypes.guess_extension(mime_type) or ".png"
    return f"{block_id}{extension}"
