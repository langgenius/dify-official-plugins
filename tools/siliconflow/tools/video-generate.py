import base64
import time
from collections.abc import Generator
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

IMAGE_TO_VIDEO_MODEL = "Wan-AI/Wan2.2-I2V-A14B"
TEXT_TO_VIDEO_MODEL = "Wan-AI/Wan2.2-T2V-A14B"
SILICONFLOW_VIDEO_SUBMIT_ENDPOINT = "https://api.siliconflow.cn/v1/video/submit"
SILICONFLOW_VIDEO_STATUS_ENDPOINT = "https://api.siliconflow.cn/v1/video/status"
REQUEST_TIMEOUT = 60
POLL_INTERVAL_SECONDS = 5
MAX_WAIT_SECONDS = 300


class VideoGenerateTool(Tool):
    def _log_message(self, message: str) -> str:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        return f"[{timestamp}] {message}"

    def _build_headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.runtime.credentials['siliconFlow_api_key']}",
        }

    def _extract_image_data(self, file_value: Any) -> str:
        if isinstance(file_value, str):
            if file_value.startswith("data:image") or file_value.startswith("http"):
                return file_value
            with open(file_value, "rb") as file_obj:
                return f"data:image/png;base64,{base64.b64encode(file_obj.read()).decode('utf-8')}"

        if hasattr(file_value, "url") and file_value.url:
            return file_value.url

        blob = getattr(file_value, "blob", None)
        if blob:
            return f"data:image/png;base64,{base64.b64encode(blob).decode('utf-8')}"

        if hasattr(file_value, "read"):
            content = file_value.read()
            if hasattr(file_value, "seek"):
                file_value.seek(0)
            return f"data:image/png;base64,{base64.b64encode(content).decode('utf-8')}"

        path = getattr(file_value, "path", None)
        if path:
            with open(path, "rb") as file_obj:
                return f"data:image/png;base64,{base64.b64encode(file_obj.read()).decode('utf-8')}"

        raise ValueError("Unable to read image input")

    def _poll_video_result(
        self, headers: dict[str, str], request_id: str
    ) -> Generator[ToolInvokeMessage, None, None]:
        yield self.create_text_message(
            self._log_message(
                f"Video generation request submitted (ID: {request_id}). Waiting for results..."
            )
        )

        waited_seconds = 0
        last_status = ""
        while waited_seconds < MAX_WAIT_SECONDS:
            try:
                response = requests.post(
                    SILICONFLOW_VIDEO_STATUS_ENDPOINT,
                    json={"requestId": request_id},
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
            except requests.RequestException as exc:
                yield self.create_text_message(
                    self._log_message(f"Warning: failed to query video status: {exc}")
                )
                time.sleep(POLL_INTERVAL_SECONDS)
                waited_seconds += POLL_INTERVAL_SECONDS
                continue

            if response.status_code != 200:
                yield self.create_text_message(
                    self._log_message(
                        f"Warning: status query failed with HTTP {response.status_code}"
                    )
                )
                time.sleep(POLL_INTERVAL_SECONDS)
                waited_seconds += POLL_INTERVAL_SECONDS
                continue

            try:
                status_data: dict[str, Any] = response.json()
            except ValueError:
                yield self.create_text_message(
                    self._log_message(
                        "Warning: status query returned a non-JSON response"
                    )
                )
                time.sleep(POLL_INTERVAL_SECONDS)
                waited_seconds += POLL_INTERVAL_SECONDS
                continue

            status = str(status_data.get("status", ""))
            if status != last_status:
                yield self.create_text_message(
                    self._log_message(
                        f"Status changed: {last_status or 'Initial'} -> {status}"
                    )
                )
                last_status = status

            if status == "Succeed":
                results = status_data.get("results")
                if isinstance(results, dict):
                    videos = results.get("videos")
                    if isinstance(videos, list) and videos:
                        first_video = videos[0]
                        if isinstance(first_video, dict):
                            video_url = first_video.get("url")
                            if isinstance(video_url, str) and video_url:
                                yield self.create_json_message(status_data)
                                yield self.create_text_message(
                                    f"Video URL: {video_url}"
                                )
                                yield self.create_text_message(
                                    self._log_message(
                                        "Video generation successful. The returned video URL is valid for 1 hour."
                                    )
                                )
                                return
                yield self.create_text_message(
                    self._log_message(
                        "Error: generation succeeded but no video URL was returned"
                    )
                )
                return

            if status == "Failed":
                reason = status_data.get("reason", "Unknown reason")
                yield self.create_text_message(
                    self._log_message(
                        f"Error: video generation failed. Reason: {reason}"
                    )
                )
                return

            if status in {"InQueue", "InProgress"}:
                time.sleep(POLL_INTERVAL_SECONDS)
                waited_seconds += POLL_INTERVAL_SECONDS
                continue

            yield self.create_text_message(
                self._log_message(
                    f"Warning: unexpected status '{status}'. Reason: {status_data.get('reason', 'Unknown')}"
                )
            )
            time.sleep(POLL_INTERVAL_SECONDS)
            waited_seconds += POLL_INTERVAL_SECONDS

        yield self.create_text_message(
            self._log_message(
                f"Notice: waited over {MAX_WAIT_SECONDS} seconds. Video may still be generating. Request ID: {request_id}"
            )
        )

    def _submit_and_poll(
        self, payload: dict[str, Any], model: str
    ) -> Generator[ToolInvokeMessage, None, None]:
        headers = self._build_headers()
        yield self.create_text_message(
            self._log_message(f"Starting video generation with model: {model}")
        )

        try:
            response = requests.post(
                SILICONFLOW_VIDEO_SUBMIT_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            yield self.create_text_message(
                f"Error: failed to submit video generation request: {exc}"
            )
            return

        if response.status_code != 200:
            yield self.create_text_message(
                f"Error: failed to submit video generation request: {response.text}"
            )
            return

        try:
            data: dict[str, Any] = response.json()
        except ValueError:
            yield self.create_text_message(
                "Error: SiliconFlow video submit returned a non-JSON response"
            )
            return

        request_id = data.get("requestId")
        if not isinstance(request_id, str) or not request_id:
            yield self.create_text_message(
                "Error: requestId was not returned by SiliconFlow"
            )
            return

        yield self.create_json_message(data)
        yield from self._poll_video_result(headers, request_id)

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        prompt = str(tool_parameters.get("prompt", "")).strip()
        if not prompt:
            yield self.create_text_message("Error: prompt is required")
            return

        model = str(tool_parameters.get("model", TEXT_TO_VIDEO_MODEL))
        if model not in {IMAGE_TO_VIDEO_MODEL, TEXT_TO_VIDEO_MODEL}:
            yield self.create_text_message("Error: unsupported video generation model")
            return

        payload = {
            "model": model,
            "prompt": prompt,
            "image_size": tool_parameters.get("video_size", "1280x720"),
            "negative_prompt": tool_parameters.get("negative_prompt"),
            "seed": tool_parameters.get("seed"),
        }

        if model == IMAGE_TO_VIDEO_MODEL:
            image_input = tool_parameters.get("image")
            if not image_input:
                yield self.create_text_message(
                    "Error: image is required when model is Wan-AI/Wan2.2-I2V-A14B"
                )
                return

            image_value = (
                image_input[0] if isinstance(image_input, list) else image_input
            )
            try:
                payload["image"] = self._extract_image_data(image_value)
            except Exception as exc:
                yield self.create_text_message(
                    f"Error: failed to process image input: {exc}"
                )
                return

        payload = {
            key: value for key, value in payload.items() if value not in (None, "")
        }
        yield from self._submit_and_poll(payload, model)
