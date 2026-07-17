import asyncio
import json
import mimetypes
from collections.abc import Generator
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

_TERMINAL_STATUSES = {"COMPLETED", "FAILED", "STOPPED"}
_DEFAULT_MCP_URL = "https://mcp.transform.unstructured.io"
_REQUIRED_TRANSFORM_TOOLS = {
    "request_file_upload_url",
    "transform_files",
    "check_transform_status",
    "get_transform_results",
}
_JOB_TIMEOUT_SECONDS = 10 * 60
_RESULTS_RETRY_SECONDS = 2


class _TransformToolError(RuntimeError):
    def __init__(self, error: dict[str, Any]) -> None:
        self.code = str(error.get("code") or "")
        super().__init__(error.get("message") or json.dumps(error))


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _raise_tool_error(error: Any) -> None:
    if isinstance(error, dict):
        raise _TransformToolError(error)
    raise RuntimeError(str(error))


def _tool_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        payload = structured.get("result", structured)
        if isinstance(payload, dict):
            if payload.get("error"):
                _raise_tool_error(payload["error"])
            if not getattr(result, "isError", False):
                return payload

    text = next(
        (
            item.text
            for item in getattr(result, "content", [])
            if getattr(item, "type", None) == "text"
        ),
        None,
    )
    if text is None:
        if getattr(result, "isError", False):
            raise RuntimeError("Transform MCP tool call failed")
        raise RuntimeError("Transform MCP returned no structured or text content")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if getattr(result, "isError", False):
            raise RuntimeError(text) from None
        raise
    if payload.get("error"):
        _raise_tool_error(payload["error"])
    return payload


def _require_https_transform_url(api_url: str) -> None:
    parsed = urlparse(api_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ToolProviderCredentialValidationError(
            "Enter a valid HTTPS Transform MCP URL"
        )


def _validate_transform_tools(names: set[str]) -> None:
    missing = sorted(_REQUIRED_TRANSFORM_TOOLS - names)
    if missing:
        raise RuntimeError(f"endpoint is missing required tools: {', '.join(missing)}")


def _redacted_url(url: Any) -> str:
    parsed = urlparse(str(url))
    return urlunparse(parsed._replace(query="", fragment=""))


def _ensure_transfer_success(response: httpx.Response, operation: str) -> None:
    if response.is_success:
        return
    raise RuntimeError(
        f"{operation} failed with HTTP {response.status_code} at "
        f"{_redacted_url(response.request.url)}"
    )


async def _get_transform_results(
    session: ClientSession,
    *,
    job_id: str,
    output_format: str,
    deadline: float,
) -> dict[str, Any]:
    while True:
        try:
            return _tool_payload(
                await session.call_tool(
                    "get_transform_results",
                    {"job_id": job_id, "output_format": output_format},
                )
            )
        except _TransformToolError as exc:
            if exc.code != "job_not_complete":
                raise
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Transform job {job_id} results were not ready within 10 minutes"
                ) from exc
            await asyncio.sleep(min(_RESULTS_RETRY_SECONDS, remaining))


def _stages(parameters: dict[str, Any]) -> dict[str, Any]:
    stages: dict[str, Any] = {}
    partition: dict[str, Any] = {}
    if strategy := parameters.get("strategy"):
        partition["strategy"] = strategy
    if languages := _split_csv(parameters.get("languages")):
        partition["languages"] = languages
    if partition:
        stages["partition"] = partition

    if enrichments := _split_csv(parameters.get("enrichments")):
        stages["enrich"] = {"types": enrichments}

    if chunking_strategy := parameters.get("chunking_strategy"):
        stages["chunk"] = {
            "strategy": chunking_strategy,
            "max_characters": int(parameters.get("max_characters") or 800),
        }

    if parameters.get("embed"):
        stages["embed"] = {}
    return stages


class TransformTool(Tool):
    @staticmethod
    def validate_credentials(credentials: dict[str, Any]) -> None:
        api_url = (credentials.get("api_url") or _DEFAULT_MCP_URL).rstrip("/")
        api_key = credentials.get("api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError(
                "Enter an Unstructured Transform API key"
            )
        _require_https_transform_url(api_url)
        try:
            asyncio.run(TransformTool._validate_connection(api_url, api_key))
        except Exception as exc:
            raise ToolProviderCredentialValidationError(
                f"Could not connect to Unstructured Transform: {exc}"
            ) from exc

    @staticmethod
    async def _validate_connection(api_url: str, api_key: str) -> None:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        ) as http_client:
            async with streamable_http_client(api_url, http_client=http_client) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    _validate_transform_tools(names)

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        credentials = self.runtime.credentials
        if credentials.get("server_type") != "transform":
            raise ToolProviderCredentialValidationError(
                "Select Unstructured Transform in the provider credentials"
            )
        api_url = (credentials.get("api_url") or _DEFAULT_MCP_URL).rstrip("/")
        api_key = credentials.get("api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError(
                "Enter an Unstructured Transform API key"
            )
        _require_https_transform_url(api_url)

        result = asyncio.run(
            self._transform(
                api_url=api_url,
                api_key=api_key,
                parameters=tool_parameters,
            )
        )

        output_format = tool_parameters.get("output_format") or "md"
        content = result["content"]
        filename = result["filename"]
        mime_type = result["mime_type"]
        if output_format == "json":
            try:
                yield self.create_json_message(json.loads(content.decode("utf-8")))
            except json.JSONDecodeError:
                yield self.create_text_message(content.decode("utf-8"))
        else:
            yield self.create_text_message(content.decode("utf-8"))

        yield self.create_blob_message(
            content,
            meta={"filename": filename, "mime_type": mime_type},
        )
        yield self.create_variable_message("job_id", result["job_id"])
        yield self.create_variable_message("output_ref", result.get("output_ref", ""))
        yield self.create_variable_message(
            "result",
            content.decode("utf-8"),
        )

    async def _transform(
        self,
        *,
        api_url: str,
        api_key: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        file = parameters.get("file")
        file_url = (parameters.get("file_url") or "").strip()
        if bool(file) == bool(file_url):
            raise ValueError("Provide exactly one of file or file_url")
        if file_url and urlparse(file_url).scheme not in {"http", "https"}:
            raise ValueError("file_url must be a public HTTP(S) URL")

        output_format = parameters.get("output_format") or "md"
        mcp_timeout = timedelta(minutes=2)
        async with (
            httpx.AsyncClient(
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=120,
            ) as mcp_http,
            httpx.AsyncClient(timeout=120, follow_redirects=True) as transfer_http,
        ):
            async with streamable_http_client(api_url, http_client=mcp_http) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=mcp_timeout,
                ) as session:
                    await session.initialize()
                    if file:
                        content_type = (
                            getattr(file, "mime_type", None)
                            or mimetypes.guess_type(file.filename)[0]
                            or "application/octet-stream"
                        )
                        upload = _tool_payload(
                            await session.call_tool(
                                "request_file_upload_url",
                                {
                                    "filename": file.filename,
                                    "content_type": content_type,
                                    "size_bytes": len(file.blob),
                                },
                            )
                        )
                        upload_response = await transfer_http.put(
                            upload["upload_url"],
                            headers=upload.get("headers") or {},
                            content=file.blob,
                        )
                        _ensure_transfer_success(upload_response, "File upload")
                        file_ref = upload["file_ref"]
                        source_name = file.filename
                    else:
                        file_ref = file_url
                        source_name = Path(urlparse(file_url).path).name or "document"

                    job = _tool_payload(
                        await session.call_tool(
                            "transform_files",
                            {"file_refs": [file_ref], "stages": _stages(parameters)},
                        )
                    )
                    job_id = job["job_id"]

                    deadline = asyncio.get_running_loop().time() + _JOB_TIMEOUT_SECONDS
                    while True:
                        status = _tool_payload(
                            await session.call_tool(
                                "check_transform_status", {"job_id": job_id}
                            )
                        )
                        state = status["status"]
                        if state in _TERMINAL_STATUSES:
                            break
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            raise TimeoutError(
                                f"Transform job {job_id} did not finish within 10 minutes"
                            )
                        poll_after = max(float(status.get("poll_after") or 30), 1)
                        await asyncio.sleep(min(poll_after, remaining))

                    if state != "COMPLETED":
                        raise RuntimeError(f"Transform job {job_id} ended with {state}")

                    results = await _get_transform_results(
                        session,
                        job_id=job_id,
                        output_format=output_format,
                        deadline=deadline,
                    )
                    first = results["files"][0]
                    if "content" in first:
                        content = first["content"].encode("utf-8")
                    else:
                        download = await transfer_http.get(first["download_url"])
                        _ensure_transfer_success(download, "Result download")
                        content = download.content

        suffix = {"md": ".md", "json": ".json", "html": ".html", "txt": ".txt"}[
            output_format
        ]
        mime_type = {
            "md": "text/markdown",
            "json": "application/json",
            "html": "text/html",
            "txt": "text/plain",
        }[output_format]
        return {
            "job_id": job_id,
            "output_ref": first.get("output_ref"),
            "filename": f"{Path(source_name).stem}{suffix}",
            "mime_type": mime_type,
            "content": content,
        }
