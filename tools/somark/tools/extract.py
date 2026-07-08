import json
import logging
import random
import time
from typing import Any, Dict, Generator, Optional

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)

# Default element formats
DEFAULT_ELEMENT_FORMATS = {
    "image": "url",
    "formula": "latex",
    "table": "html",
    "cs": "image",
}

# Supported element formats
SUPPORTED_ELEMENT_FORMATS = {
    "image": ["url", "base64", "none"],
    "formula": ["latex", "mathml", "ascii"],
    "table": ["markdown", "html", "image"],
    "cs": ["image"],
}

# ---------- Retry / Polling configuration ----------

# SoMark concurrency rate-limit code; retry with backoff when hit during submit
QPS_LIMIT_CODE = 1124

# Submit phase: limited retries when "concurrency slots are full" is rejected
SUBMIT_BUDGET_SECONDS = 10 * 60  # total time budget for submit retries (10 minutes)
SUBMIT_BACKOFF_BASE_SECONDS = 1.0  # initial backoff duration
SUBMIT_BACKOFF_MAX_SECONDS = 10.0  # max backoff per attempt
SUBMIT_BACKOFF_JITTER_SECONDS = 0.5  # backoff jitter to avoid concurrent calls colliding
SUBMIT_REQUEST_TIMEOUT = 60  # timeout for a single submit request

# Poll phase: keep querying task status until SUCCESS / FAILED / budget exhausted
POLL_BUDGET_SECONDS = 10 * 60  # max wait time for a single task
POLL_INTERVAL_BASE_SECONDS = 2.0  # initial polling interval
POLL_INTERVAL_MAX_SECONDS = 10.0  # max polling interval for long tasks
POLL_INTERVAL_GROWTH = 1.5  # interval growth factor after each poll
POLL_REQUEST_TIMEOUT = 30  # timeout for a single status query request


def _extract_error_detail(
    payload: Optional[Dict[str, Any]], fallback: str = "unknown error"
) -> str:
    """Extract the most descriptive error text from a SoMark response."""
    if not isinstance(payload, dict):
        return f"{fallback} (raw response: {payload!r})"

    # Priority: message > msg > error > data.message > data.error > full payload
    for key in ("message", "msg", "error", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return f"code={payload.get('code')}, {key}={value}"

    data_block = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if data_block:
        for key in ("message", "msg", "error", "detail"):
            value = data_block.get(key)
            if isinstance(value, str) and value.strip():
                return f"code={payload.get('code')}, data.{key}={value}"

    # Fallback: serialize the full payload to help with diagnosis
    try:
        return f"code={payload.get('code')}, payload={json.dumps(payload, ensure_ascii=False)}"
    except Exception:
        return f"code={payload.get('code')}, payload={payload!r}"


def _build_connection_error(base_url: str, endpoint: str) -> str:
    protocol = "HTTPS" if base_url.startswith("https://") else "HTTP"
    host = base_url.replace("https://", "").replace("http://", "")
    return (
        f"Failed to connect to the SoMark service at {host}{endpoint} over {protocol}. "
        f"Please make sure the service is running and reachable from the plugin runtime"
    )


class ExtractTool(Tool):
    def _create_error_log(
        self,
        stage: str,
        message: str,
        data: Dict[str, Any] | None = None,
    ) -> ToolInvokeMessage:
        payload = {"stage": stage, "message": message}
        if data:
            payload.update(data)

        return self.create_log_message(
            label=f"SoMark Document Parser: {stage}",
            data=payload,
            status=InvokeMessage.LogMessage.LogStatus.ERROR,
        )

    def _create_info_log(
        self,
        stage: str,
        message: str,
        data: Dict[str, Any] | None = None,
    ) -> ToolInvokeMessage:
        payload = {"stage": stage, "message": message}
        if data:
            payload.update(data)

        return self.create_log_message(
            label=f"SoMark Document Parser: {stage}",
            data=payload,
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

    # ---------- SoMark async API ----------
    #
    # Called via `yield from`: the sub-generator yields progress logs along the way,
    # and finally uses `return value` to hand the result back to the `_invoke` main flow.

    def _submit_task(
        self,
        base_url: str,
        files: Dict[str, Any],
        data: Dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, str]:
        """
        Submit a parsing task. Retry with exponential backoff when QPS rate-limited
        (code=1124); raise immediately on other business errors. Returns task_id.
        """
        deadline = time.monotonic() + SUBMIT_BUDGET_SECONDS
        attempt = 0

        yield self._create_info_log(
            stage="submit_task",
            message="Submitting file to SoMark async pipeline",
        )

        while True:
            try:
                response = requests.post(
                    f"{base_url}/parse/async",
                    files=files,
                    data=data,
                    timeout=SUBMIT_REQUEST_TIMEOUT,
                )
            except requests.RequestException as e:
                raise RuntimeError(
                    _build_connection_error(base_url, "/parse/async")
                ) from e

            try:
                payload = response.json()
            except ValueError:
                raise RuntimeError(
                    f"SoMark service returned a non-JSON response (HTTP {response.status_code})"
                )

            code = payload.get("code") if isinstance(payload, dict) else None
            data_block = payload.get("data") if isinstance(payload, dict) else None
            task_id = (
                data_block.get("task_id") if isinstance(data_block, dict) else None
            )

            if code == 0 and task_id:
                yield self._create_info_log(
                    stage="submit_task",
                    message="Task submitted successfully",
                    data={"task_id": task_id, "attempts": attempt + 1},
                )
                return task_id

            # Concurrency slot / QPS rejection: back off within budget then retry
            if code == QPS_LIMIT_CODE:
                backoff = min(
                    SUBMIT_BACKOFF_BASE_SECONDS * (2**attempt),
                    SUBMIT_BACKOFF_MAX_SECONDS,
                )
                wait = backoff + random.random() * SUBMIT_BACKOFF_JITTER_SECONDS
                if time.monotonic() + wait > deadline:
                    raise RuntimeError(
                        "SoMark service is currently busy (QPS limit). "
                        "Please retry later or reduce workflow concurrency"
                    )
                logger.info(
                    "SoMark submit hit QPS limit, retrying in %.2fs (attempt %d)",
                    wait,
                    attempt + 1,
                )
                yield self._create_info_log(
                    stage="submit_task",
                    message=f"SoMark is busy (QPS limit), backing off {wait:.2f}s before retry",
                    data={"attempt": attempt + 1, "wait_seconds": round(wait, 2)},
                )
                time.sleep(wait)
                attempt += 1
                continue

            # Other business errors: raise immediately, no retry
            raise RuntimeError(f"SoMark API error: {_extract_error_detail(payload)}")

    def _poll_task(
        self,
        base_url: str,
        api_key: str,
        task_id: str,
    ) -> Generator[ToolInvokeMessage, None, Dict[str, Any]]:
        """
        Poll task status until SUCCESS / FAILED / budget exhausted.
        Polling interval grows by POLL_INTERVAL_GROWTH, capped at POLL_INTERVAL_MAX_SECONDS.
        Returns outputs.
        """
        deadline = time.monotonic() + POLL_BUDGET_SECONDS
        interval = POLL_INTERVAL_BASE_SECONDS
        started_at = time.monotonic()
        poll_count = 0

        yield self._create_info_log(
            stage="poll_task",
            message="Polling task status",
            data={"task_id": task_id},
        )

        while time.monotonic() < deadline:
            time.sleep(interval)
            poll_count += 1

            try:
                response = requests.post(
                    f"{base_url}/parse/async_check",
                    data={"api_key": api_key, "task_id": task_id},
                    timeout=POLL_REQUEST_TIMEOUT,
                )
            except requests.RequestException as e:
                raise RuntimeError(
                    _build_connection_error(base_url, "/parse/async_check")
                ) from e

            try:
                payload = response.json()
            except ValueError:
                raise RuntimeError(
                    f"SoMark service returned a non-JSON response (HTTP {response.status_code})"
                )

            code = payload.get("code") if isinstance(payload, dict) else None
            if code != 0:
                raise RuntimeError(
                    f"SoMark API error: {_extract_error_detail(payload)}"
                )

            data_block = payload.get("data") if isinstance(payload, dict) else None
            status = data_block.get("status") if isinstance(data_block, dict) else None
            elapsed = round(time.monotonic() - started_at, 1)

            if status == "SUCCESS":
                yield self._create_info_log(
                    stage="poll_task",
                    message=f"Task completed in {elapsed}s",
                    data={
                        "task_id": task_id,
                        "polls": poll_count,
                        "elapsed_seconds": elapsed,
                    },
                )
                result = (
                    data_block.get("result") if isinstance(data_block, dict) else None
                )
                outputs = result.get("outputs") if isinstance(result, dict) else None
                return outputs if isinstance(outputs, dict) else {}

            if status == "FAILED":
                raise RuntimeError(
                    f"SoMark task failed: {_extract_error_detail(payload, 'task failed')}"
                )

            # QUEUING / PROCESSING → grow the polling interval and keep waiting
            yield self._create_info_log(
                stage="poll_task",
                message=f"Task status: {status or 'unknown'} ({elapsed}s elapsed, next check in {interval:.1f}s)",
                data={
                    "task_id": task_id,
                    "status": status,
                    "poll": poll_count,
                    "elapsed_seconds": elapsed,
                    "next_interval_seconds": round(interval, 2),
                },
            )
            interval = min(interval * POLL_INTERVAL_GROWTH, POLL_INTERVAL_MAX_SECONDS)

        raise RuntimeError(
            f"SoMark task {task_id} timed out after {POLL_BUDGET_SECONDS}s while waiting for completion"
        )

    # ---------- Tool main flow ----------

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the SoMark extraction tool via the async pipeline:
          1. POST /parse/async         -- submit the file and get task_id (retry with backoff on QPS limit)
          2. POST /parse/async_check   -- poll task status until SUCCESS / FAILED / budget exhausted
        """

        # Get the file parameter
        file = tool_parameters.get("file")
        if not file:
            yield self.create_text_message("Error: No file provided.")
            return

        # Get the output_formats parameter (single choice: markdown / json / both)
        output_format_choice = (tool_parameters.get("output_formats") or "both").strip().lower()
        if output_format_choice == "markdown":
            output_formats = ["markdown"]
        elif output_format_choice == "json":
            output_formats = ["json"]
        else:
            output_formats = ["markdown", "json"]

        # Get the element_formats parameter
        element_formats = {
            "image": tool_parameters.get("element_formats_image")
            or DEFAULT_ELEMENT_FORMATS["image"],
            "formula": tool_parameters.get("element_formats_formula")
            or DEFAULT_ELEMENT_FORMATS["formula"],
            "table": tool_parameters.get("element_formats_table")
            or DEFAULT_ELEMENT_FORMATS["table"],
            "cs": tool_parameters.get("element_formats_cs")
            or DEFAULT_ELEMENT_FORMATS["cs"],
        }
        for k, v in element_formats.items():
            if v not in SUPPORTED_ELEMENT_FORMATS[k]:
                supported_values = ", ".join(SUPPORTED_ELEMENT_FORMATS[k])
                error_msg = (
                    f"Invalid element_formats_{k} value '{v}'. "
                    f"Supported values: {supported_values}."
                )
                yield self._create_error_log(
                    stage="validate_parameters",
                    message=error_msg,
                    data={
                        "parameter": f"element_formats_{k}",
                        "value": v,
                        "supported_values": SUPPORTED_ELEMENT_FORMATS[k],
                    },
                )
                raise ValueError(error_msg)

        # Get the feature_config parameter
        feature_config = {
            "enable_text_cross_page": tool_parameters.get(
                "feature_config_enable_text_cross_page"
            ),
            "enable_table_cross_page": tool_parameters.get(
                "feature_config_enable_table_cross_page"
            ),
            "enable_title_level_recognition": tool_parameters.get(
                "feature_config_enable_title_level_recognition"
            ),
            "enable_inline_image": tool_parameters.get(
                "feature_config_enable_inline_image"
            ),
            "enable_table_image": tool_parameters.get(
                "feature_config_enable_table_image"
            ),
            "enable_image_understanding": tool_parameters.get(
                "feature_config_enable_image_understanding"
            ),
            "keep_header_footer": tool_parameters.get(
                "feature_config_keep_header_footer"
            ),
        }

        # Get credential parameters
        base_url = (self.runtime.credentials.get("base_url") or "").strip().rstrip("/")
        api_key = (self.runtime.credentials.get("api_key") or "").strip()

        # Build the request body
        files = {"file": (file.filename, file.blob, file.mime_type)}
        data = {
            "api_key": api_key,
            "output_formats": output_formats,
            "element_formats": json.dumps(element_formats, ensure_ascii=False),
            "feature_config": json.dumps(feature_config, ensure_ascii=False),
        }

        # Submit the task (exponential backoff on QPS limit)
        try:
            task_id = yield from self._submit_task(base_url, files, data)
        except RuntimeError as e:
            error_msg = str(e)
            logger.error(error_msg)
            yield self._create_error_log(stage="submit_task", message=error_msg)
            raise

        logger.info("SoMark task submitted: task_id=%s", task_id)

        # Poll the task status
        try:
            outputs = yield from self._poll_task(base_url, api_key, task_id)
        except RuntimeError as e:
            error_msg = str(e)
            logger.error(error_msg)
            yield self._create_error_log(
                stage="poll_task",
                message=error_msg,
                data={"task_id": task_id},
            )
            raise

        # Parse outputs
        md_content = ""
        json_content = ""

        if isinstance(outputs, dict):
            md_value = outputs.get("markdown")
            if isinstance(md_value, str) and md_value.strip():
                md_content = md_value
            json_value = outputs.get("json")
            if json_value not in (None, "", [], {}):
                json_content = json.dumps(json_value, ensure_ascii=False)

        if not md_content and not json_content:
            error_msg = "SoMark response has no outputs"
            yield self._create_error_log(
                stage="parse_response",
                message=error_msg,
                data={"task_id": task_id},
            )
            raise RuntimeError(error_msg)

        if json_content:
            yield self.create_variable_message("json_str", json_content)
        if md_content:
            yield self.create_variable_message("markdown", md_content)

        yield self.create_json_message(
            {
                "task_id": task_id,
                "outputs": outputs,
            }
        )
