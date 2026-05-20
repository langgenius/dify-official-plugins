import ast
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

# 默认元素格式
DEFAULT_ELEMENT_FORMATS = {
    "image": "url",
    "formula": "latex",
    "table": "html",
    "cs": "image",
}

# 支持的元素格式
SUPPORTED_ELEMENT_FORMATS = {
    "image": ["url", "base64", "none"],
    "formula": ["latex", "mathml", "ascii"],
    "table": ["markdown", "html", "image"],
    "cs": ["image"],
}

# ---------- 重试 / 轮询 配置 ----------

# SoMark 并发限流错误码；提交阶段命中该码时按退避策略重试
QPS_LIMIT_CODE = 1124

# 提交阶段：对 "并发槽位已满" 的拒绝做有限重试
SUBMIT_BUDGET_SECONDS = 10 * 60  # 提交重试的总时间预算（10 分钟）
SUBMIT_BACKOFF_BASE_SECONDS = 1.0  # 起始退避时长
SUBMIT_BACKOFF_MAX_SECONDS = 10.0  # 单次退避上限
SUBMIT_BACKOFF_JITTER_SECONDS = 0.5  # 退避抖动，避免多并发调用同步撞车
SUBMIT_REQUEST_TIMEOUT = 60  # 单次提交请求超时

# 轮询阶段：持续查询任务状态直至成功 / 失败 / 预算耗尽
POLL_BUDGET_SECONDS = 10 * 60  # 单任务的最长等待时长
POLL_INTERVAL_BASE_SECONDS = 2.0  # 轮询起始间隔
POLL_INTERVAL_MAX_SECONDS = 10.0  # 长任务的轮询间隔上限
POLL_INTERVAL_GROWTH = 1.5  # 每次轮询后的间隔放大倍数
POLL_REQUEST_TIMEOUT = 30  # 单次查询请求超时


def _extract_error_detail(
    payload: Optional[Dict[str, Any]], fallback: str = "unknown error"
) -> str:
    """从 SoMark 响应里提取最具描述性的错误文本。"""
    if not isinstance(payload, dict):
        return fallback
    data_block = payload.get("data") if isinstance(payload.get("data"), dict) else None

    return payload.get("message") or fallback


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

    # ---------- SoMark 异步接口 ----------
    #
    # 用 `yield from` 调用：子生成器一路 yield 进度日志，
    # 最终用 `return value` 把结果返还给 `_invoke` 主流程。

    def _submit_task(
        self,
        base_url: str,
        files: Dict[str, Any],
        data: Dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, str]:
        """
        提交解析任务。命中 QPS 限流（code=1124）时按指数退避重试，
        其它业务错误立即抛出。返回 task_id。
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

            # 并发槽位 / QPS 拒绝：在预算内退避后重试
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

            # 其它业务错误：立即抛出，不重试
            raise RuntimeError(f"SoMark API error: {_extract_error_detail(payload)}")

    def _poll_task(
        self,
        base_url: str,
        api_key: str,
        task_id: str,
    ) -> Generator[ToolInvokeMessage, None, Dict[str, Any]]:
        """
        轮询任务状态直至 SUCCESS / FAILED / 预算耗尽。
        轮询间隔按 POLL_INTERVAL_GROWTH 倍增，上限 POLL_INTERVAL_MAX_SECONDS。
        返回 outputs。
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

            # QUEUING / PROCESSING → 拉长轮询间隔后继续等
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

    # ---------- 工具主流程 ----------

    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the SoMark extraction tool via the async pipeline:
          1. POST /parse/async         —— 提交文件，拿到 task_id（命中 QPS 限流时按退避策略重试）
          2. POST /parse/async_check   —— 轮询任务状态，直到 SUCCESS / FAILED / 预算耗尽
        """

        # 获取文件参数
        file = tool_parameters.get("file")
        if not file:
            yield self.create_text_message("Error: No file provided.")
            return

        # 获取output_formats参数
        output_formats = tool_parameters.get("output_formats") or ["json", "markdown"]
        if isinstance(output_formats, str):
            output_formats = ast.literal_eval(output_formats)

        # 获取element_formats参数
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

        # 获取feature_config参数
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

        # 获取凭证参数
        base_url = (self.runtime.credentials.get("base_url") or "").strip().rstrip("/")
        api_key = (self.runtime.credentials.get("api_key") or "").strip()

        # 构造请求体
        files = {"file": (file.filename, file.blob, file.mime_type)}
        data = {
            "api_key": api_key,
            "output_formats": output_formats,
            "element_formats": json.dumps(element_formats, ensure_ascii=False),
            "feature_config": json.dumps(feature_config, ensure_ascii=False),
        }

        # 提交任务（QPS 限流时指数退避）
        try:
            task_id = yield from self._submit_task(base_url, files, data)
        except RuntimeError as e:
            error_msg = str(e)
            logger.error(error_msg)
            yield self._create_error_log(stage="submit_task", message=error_msg)
            raise

        logger.info("SoMark task submitted: task_id=%s", task_id)

        # 轮询任务状态
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

        # 解析 outputs
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
