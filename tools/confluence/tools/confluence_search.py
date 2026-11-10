from collections.abc import Generator
from typing import Any
from urllib.parse import parse_qsl, urlparse

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.confluence_client import ConfluenceAuthError, clamp, confluence_request, resolve_context
from tools.outputs import with_outputs


def cql_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_cql(tool_parameters: dict[str, Any]) -> str:
    """The CQL to run: the given query, or one built from text / space / label / type."""
    cql = str(tool_parameters.get("cql") or "").strip()
    if cql:
        return cql
    text = str(tool_parameters.get("text") or "").strip()
    space = str(tool_parameters.get("space_key") or "").strip()
    label = str(tool_parameters.get("label") or "").strip()
    if not (text or space or label):
        raise ConfluenceAuthError("Give a CQL query, or at least one of text, space_key or label.")
    parts = []
    if text:
        parts.append(f"text ~ {cql_string(text)}")
    if space:
        parts.append(f"space = {cql_string(space)}")
    if label:
        parts.append(f"label = {cql_string(label)}")
    content_type = str(tool_parameters.get("content_type") or "page").strip()
    if content_type != "any":
        parts.append(f"type = {cql_string(content_type)}")
    return " AND ".join(parts) + " ORDER BY lastmodified DESC"


def result_dict(ctx, result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content") or {}
    return {
        "id": str(content.get("id", "")),
        "type": content.get("type", ""),
        "title": content.get("title") or result.get("title", ""),
        "space": (result.get("resultGlobalContainer") or {}).get("title", ""),
        "excerpt": (result.get("excerpt") or "").replace("@@@hl@@@", "").replace("@@@endhl@@@", ""),
        "last_modified": result.get("lastModified", ""),
        "url": ctx.web(result.get("url") or (content.get("_links") or {}).get("webui", "")),
    }


class ConfluenceSearchTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Search pages and other content with CQL, or with simple text / space / label filters."""
        limit = clamp(tool_parameters.get("limit"), 25, 200)
        try:
            ctx = resolve_context(self.runtime.credentials, self)
            cql = build_cql(tool_parameters)
            results: list[dict[str, Any]] = []
            params: dict[str, Any] = {"cql": cql, "limit": min(50, limit)}
            while len(results) < limit:
                body = confluence_request(ctx, "GET", ctx.v1("search"), params=params).json()
                batch = body.get("results") or []
                results.extend(batch)
                next_link = (body.get("_links") or {}).get("next") or ""
                if not batch or not next_link:
                    break
                # The next link carries the cursor (already URL-encoded) with next=true and start; reuse its
                # decoded query as the parameters, with our own page size.
                params = {**dict(parse_qsl(urlparse(next_link).query)), "limit": min(50, limit - len(results))}
        except ConfluenceAuthError as e:
            yield self.create_text_message(str(e))
            return
        items = [result_dict(ctx, r) for r in results[:limit]]
        self._out.update(results=items, count=len(items), success=True)
        yield self.create_json_message({"cql": cql, "results": items})
        yield self.create_text_message(
            f"Found {len(items)} result(s): " + "; ".join(f"{i['title']} (id {i['id']})" for i in items[:10])
            if items
            else f"Nothing matches: {cql}"
        )
