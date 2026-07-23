import asyncio
import ipaddress
import json
import mimetypes
import socket
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
    "start_transform_job",
    "check_job_status",
    "get_job_results",
}
_JOB_TIMEOUT_SECONDS = 10 * 60
_RESULTS_RETRY_SECONDS = 2
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_MAX_RESULT_BYTES = 50 * 1024 * 1024


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


def _require_hosted_transform_url(api_url: str) -> None:
    parsed = urlparse(api_url)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    if (
        parsed.scheme != "https"
        or parsed.hostname != "mcp.transform.unstructured.io"
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ToolProviderCredentialValidationError(
            f"Use the hosted Transform MCP HTTPS URL: {_DEFAULT_MCP_URL}"
        )


def _validate_transform_tools(names: set[str]) -> None:
    missing = sorted(_REQUIRED_TRANSFORM_TOOLS - names)
    if missing:
        raise RuntimeError(f"endpoint is missing required tools: {', '.join(missing)}")


def _validate_upload_size(size_bytes: int) -> None:
    if size_bytes > _MAX_UPLOAD_BYTES:
        raise ValueError("Transform supports files up to 50 MB")


def _require_public_file_url(url: str) -> None:
    parsed = urlparse(url)
    try:
        parsed.port
    except ValueError:
        raise ValueError("file_url must be a public HTTP(S) URL") from None
    hostname = parsed.hostname
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("file_url must be a public HTTP(S) URL")

    normalized_host = hostname.rstrip(".").lower()
    if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
        raise ValueError("file_url must be a public HTTP(S) URL")
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("file_url must be a public HTTP(S) URL")


def _redacted_url(url: Any) -> str:
    parsed = urlparse(str(url))
    return urlunparse(parsed._replace(query="", fragment=""))


async def _require_public_https_transfer_url(url: Any, operation: str) -> None:
    parsed = urlparse(str(url))
    try:
        port = parsed.port
    except ValueError:
        port = -1
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or not hostname
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise RuntimeError(
            f"{operation} requires a public HTTPS URL at {_redacted_url(url)}"
        )

    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            resolved = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                port or 443,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise RuntimeError(
                f"{operation} URL host could not be resolved: {_redacted_url(url)}"
            ) from exc
        addresses = {ipaddress.ip_address(item[4][0]) for item in resolved}

    if not addresses or any(not address.is_global for address in addresses):
        raise RuntimeError(
            f"{operation} requires a public HTTPS URL at {_redacted_url(url)}"
        )


def _ensure_transfer_success(response: httpx.Response, operation: str) -> None:
    if response.is_success:
        return
    raise RuntimeError(
        f"{operation} failed with HTTP {response.status_code} at "
        f"{_redacted_url(response.request.url)}"
    )


def _raise_result_too_large(job_id: str, output_ref: Any) -> None:
    reference = f" Output reference: {output_ref}." if output_ref else ""
    raise RuntimeError(
        f"Transform result for job {job_id} exceeds Dify's 50 MB inline "
        f"result limit.{reference}"
    )


def _validate_result_size(size_bytes: int, job_id: str, output_ref: Any) -> None:
    if size_bytes > _MAX_RESULT_BYTES:
        _raise_result_too_large(job_id, output_ref)


async def _download_result(
    client: httpx.AsyncClient,
    *,
    url: Any,
    job_id: str,
    output_ref: Any,
) -> bytes:
    await _require_public_https_transfer_url(url, "Result download")
    async with client.stream("GET", str(url)) as response:
        _ensure_transfer_success(response, "Result download")
        raw_content_length = response.headers.get("content-length")
        if raw_content_length:
            try:
                _validate_result_size(
                    int(raw_content_length),
                    job_id,
                    output_ref,
                )
            except ValueError:
                pass

        content = bytearray()
        async for chunk in response.aiter_bytes():
            _validate_result_size(len(content) + len(chunk), job_id, output_ref)
            content.extend(chunk)
    return bytes(content)


async def _get_job_results(
    session: ClientSession,
    *,
    job_id: str,
    output_format: str,
    deadline: float,
) -> dict[str, Any]:
    while True:
        try:
            arguments = {"job_id": job_id, "output_format": output_format}
            if output_format == "json":
                arguments["image_base64"] = "none"
            return _tool_payload(
                await session.call_tool(
                    "get_job_results",
                    arguments,
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
        raw_max_characters = parameters.get("max_characters")
        max_characters = 800 if raw_max_characters is None else int(raw_max_characters)
        if max_characters <= 0:
            raise ValueError("max_characters must be greater than zero")
        stages["chunk"] = {
            "strategy": chunking_strategy,
            "max_characters": max_characters,
        }

    if parameters.get("embed"):
        stages["embed"] = {}
    return stages


class TransformTool(Tool):
    @staticmethod
    def validate_credentials(credentials: dict[str, Any]) -> None:
        api_url = (credentials.get("api_url") or _DEFAULT_MCP_URL).strip().rstrip("/")
        api_key = credentials.get("api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError(
                "Enter an Unstructured Transform API key"
            )
        _require_hosted_transform_url(api_url)
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
        api_url = (credentials.get("api_url") or _DEFAULT_MCP_URL).strip().rstrip("/")
        api_key = credentials.get("api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError(
                "Enter an Unstructured Transform API key"
            )
        _require_hosted_transform_url(api_url)

        result = asyncio.run(
            self._transform(
                api_url=api_url,
                api_key=api_key,
                parameters=tool_parameters,
            )
        )

        output_format = tool_parameters.get("output_format") or "md"
        content = result["content"]
        text_content = content.decode("utf-8")
        filename = result["filename"]
        mime_type = result["mime_type"]
        if output_format == "json":
            try:
                yield self.create_json_message(json.loads(text_content))
            except json.JSONDecodeError:
                yield self.create_text_message(text_content)
        else:
            yield self.create_text_message(text_content)

        yield self.create_blob_message(
            content,
            meta={"filename": filename, "mime_type": mime_type},
        )
        yield self.create_variable_message("job_id", result["job_id"])
        yield self.create_variable_message("output_ref", result.get("output_ref") or "")
        yield self.create_variable_message(
            "result",
            text_content,
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
        if file_url:
            _require_public_file_url(file_url)

        output_format = parameters.get("output_format") or "md"
        mcp_timeout = timedelta(minutes=2)
        async with (
            httpx.AsyncClient(
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=120,
            ) as mcp_http,
            httpx.AsyncClient(timeout=120, follow_redirects=False) as transfer_http,
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
                        _validate_upload_size(len(file.blob))
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
                        await _require_public_https_transfer_url(
                            upload["upload_url"], "File upload"
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
                            "start_transform_job",
                            {"file_refs": [file_ref], "stages": _stages(parameters)},
                        )
                    )
                    job_id = job["job_id"]

                    deadline = asyncio.get_running_loop().time() + _JOB_TIMEOUT_SECONDS
                    while True:
                        status = _tool_payload(
                            await session.call_tool(
                                "check_job_status", {"job_id": job_id}
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

                    results = await _get_job_results(
                        session,
                        job_id=job_id,
                        output_format=output_format,
                        deadline=deadline,
                    )
                    first = results["files"][0]
                    if "content" in first:
                        content = first["content"].encode("utf-8")
                        _validate_result_size(
                            len(content),
                            job_id,
                            first.get("output_ref"),
                        )
                    else:
                        content = await _download_result(
                            transfer_http,
                            url=first["download_url"],
                            job_id=job_id,
                            output_ref=first.get("output_ref"),
                        )

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
