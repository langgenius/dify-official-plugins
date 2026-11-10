from collections.abc import Generator
from typing import Any
import json
import re

import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient
from tools.notion_properties import InvalidPropertyValueError, build_properties_payload, is_empty, to_rich_text

# Notion accepts at most 100 child blocks per create / append request
MAX_BLOCKS_PER_REQUEST = 100

# Notion rejects request bodies over 500 KB; keep each request's content well under that
MAX_CONTENT_BYTES_PER_REQUEST = 400_000

# Creating a page and appending blocks are not idempotent, so they are sent once with a timeout
# instead of being retried after a network error (a retry could create a duplicate record)
WRITE_REQUEST_OPTIONS = {"retry_network_errors": False, "timeout": 60}

LINE_BREAK_PATTERN = re.compile(r"\r\n|\r|\n")


def _json_size(value: Any) -> int:
    # Matches how requests serialises the body (ASCII-escaped JSON)
    return len(json.dumps(value))


def _content_blocks(content: str) -> list[dict]:
    """Turn plain text into one paragraph block per line, keeping blank lines as empty paragraphs."""
    blocks = []
    for number, line in enumerate(LINE_BREAK_PATTERN.split(content.strip("\r\n")), start=1):
        try:
            rich_text = to_rich_text("content", line) if line else []
        except InvalidPropertyValueError:
            raise InvalidPropertyValueError(f"Content line {number} is too long. Split it into shorter lines.")
        block = {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text}}
        if _json_size(block) > MAX_CONTENT_BYTES_PER_REQUEST:
            raise InvalidPropertyValueError(f"Content line {number} is too long. Split it into shorter lines.")
        blocks.append(block)
    return blocks


def _batch_blocks(blocks: list[dict], first_batch_budget: int) -> list[list[dict]]:
    """Split blocks into request-sized batches by count and serialised size.
    The first batch is sent with the create request, so it also shares that request's
    size with the properties; it may be empty when the properties are large."""
    batches, current, size, budget = [], [], 0, first_batch_budget
    for block in blocks:
        block_size = _json_size(block)
        if len(current) == MAX_BLOCKS_PER_REQUEST or size + block_size > budget:
            batches.append(current)
            current, size, budget = [], 0, MAX_CONTENT_BYTES_PER_REQUEST
        current.append(block)
        size += block_size
    batches.append(current)
    return batches


class CreateDatabaseRecordTool(Tool):
    def _result(self, status: str, message: str, **fields: Any) -> Generator[ToolInvokeMessage, None, None]:
        yield self.create_text_message(message)
        yield self.create_json_message({"status": status, "message": message, **fields})

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        database_id = str(tool_parameters.get("database_id") or "").strip()
        properties_json = tool_parameters.get("properties") or ""
        content = str(tool_parameters.get("content") or "")

        # Validate parameters
        if not database_id:
            yield from self._result("invalid_input", "database_id is required.")
            return

        try:
            values = json.loads(properties_json) if isinstance(properties_json, str) else properties_json
        except json.JSONDecodeError:
            yield from self._result("invalid_input", "Invalid JSON format for properties. Please provide a valid JSON object.")
            return
        if not isinstance(values, dict) or not values:
            yield from self._result("invalid_input", "Properties must be a non-empty JSON object with property names as keys.")
            return
        # A new record starts empty, so empty values are simply left unset
        values = {name: value for name, value in values.items() if not is_empty(value)}
        if not values and not content.strip():
            yield from self._result(
                "invalid_input", "All property values are empty and no content was given, so there is nothing to create."
            )
            return

        # Get integration token from credentials
        integration_token = self.runtime.credentials.get("integration_token")
        if not integration_token:
            yield from self._result("error", "Notion Integration Token is required.")
            return

        # Initialize the Notion client
        client = NotionClient(integration_token)

        # Resolve the database schema and convert the values for their property types
        try:
            blocks = _content_blocks(content) if content.strip() else []
            data_source = client.resolve_data_source(database_id)
            data_source_id = data_source.get("id", "")
            property_types = {name: data.get("type") for name, data in data_source.get("properties", {}).items()}
            properties = build_properties_payload(values, property_types)
        except InvalidPropertyValueError as e:
            yield from self._result("invalid_input", str(e))
            return
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                yield from self._result(
                    "not_accessible",
                    f"Database {database_id} was not found or is not shared with this integration. "
                    "In Notion, open the database (or its parent page), choose ... > Connections, and add the integration.",
                )
            else:
                yield from self._result("error", f"Error retrieving database {database_id}: {e}")
            return
        except Exception as e:
            yield from self._result("error", f"Error retrieving database {database_id}: {e}")
            return

        batches = _batch_blocks(blocks, MAX_CONTENT_BYTES_PER_REQUEST - _json_size(properties))

        # Create the record with the first batch of content blocks
        try:
            page = client.create_page(
                parent={"type": "data_source_id", "data_source_id": data_source_id},
                properties=properties,
                children=batches[0],
                **WRITE_REQUEST_OPTIONS,
            )
        except requests.HTTPError as e:
            yield from self._result("error", f"Error creating record in database {database_id}: {e}")
            return
        except requests.RequestException as e:
            yield from self._result(
                "error",
                f"Error creating record in database {database_id}: {e}. "
                "The request may have reached Notion, so check the database for the record before retrying.",
            )
            return
        except Exception as e:
            yield from self._result("error", f"Error creating record in database {database_id}: {e}")
            return

        page_id = page.get("id", "")
        record = {"id": page_id, "url": page.get("url") or client.format_page_url(page_id)}

        # Append any remaining content; the record already exists, so report a failure as partial
        added = len(batches[0])
        for batch in batches[1:]:
            try:
                client.append_block_children(page_id, batch, **WRITE_REQUEST_OPTIONS)
            except Exception as e:
                yield from self._result(
                    "partially_created",
                    f"Created record {page_id}, but failed to add its content after {added} of {len(blocks)} lines: {e}",
                    record=record,
                    set_properties=list(properties),
                )
                return
            added += len(batch)

        yield from self._result(
            "created",
            f"Successfully created record {page_id}" + (f": {', '.join(properties)}" if properties else ""),
            record=record,
            set_properties=list(properties),
        )
