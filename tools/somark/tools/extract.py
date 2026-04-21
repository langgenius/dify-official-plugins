import ast
import logging
import json
from typing import Any, Dict, Generator
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
            label=f"SoMark Extract: {stage}",
            data=payload,
            status=InvokeMessage.LogMessage.LogStatus.ERROR,
        )

    def _invoke(
            self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:

        """
        Invoke the Somark extraction tool.
        """

        # 1. Get parameters
        file = tool_parameters.get("file")  # 获取file参数

        if not file:
            yield self.create_text_message("Error: No file provided.")
            return

        # 获取output_formats参数
        output_formats = tool_parameters.get("output_formats") or ["json", "markdown"]

        if isinstance(output_formats, str):
            output_formats = ast.literal_eval(output_formats)

        # 获取element_formats参数
        element_formats = {
            "image": tool_parameters.get("element_formats_image") or DEFAULT_ELEMENT_FORMATS["image"],
            "formula": tool_parameters.get("element_formats_formula") or DEFAULT_ELEMENT_FORMATS["formula"],
            "table": tool_parameters.get("element_formats_table") or DEFAULT_ELEMENT_FORMATS["table"],
            "cs": tool_parameters.get("element_formats_cs") or DEFAULT_ELEMENT_FORMATS["cs"],
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
            "enable_text_cross_page": tool_parameters.get("feature_config_enable_text_cross_page"),
            "enable_table_cross_page": tool_parameters.get("feature_config_enable_table_cross_page"),
            "enable_title_level_recognition": tool_parameters.get("feature_config_enable_title_level_recognition"),
            "enable_inline_image": tool_parameters.get("feature_config_enable_inline_image"),
            "enable_table_image": tool_parameters.get("feature_config_enable_table_image"),
            "enable_image_understanding": tool_parameters.get("feature_config_enable_image_understanding"),
            "keep_header_footer": tool_parameters.get("feature_config_keep_header_footer"),
        }

        # 2. Get configuration
        base_url = self.runtime.credentials.get("base_url")
        if not base_url:
            base_url = "https://somark.tech/api/v1"

        api_key = self.runtime.credentials.get("api_key")
        if not api_key:
            error_msg = "API Key is required."
            yield self._create_error_log(
                stage="validate_credentials",
                message=error_msg,
            )
            raise ValueError(error_msg)

        # 3. Construct URL
        base_url = base_url.rstrip("/")
        url = f"{base_url}/parse/sync"

        # 4. Prepare request
        try:
            files = {"file": (file.filename, file.blob, file.mime_type)}

            data = {
                "output_formats": output_formats,
                "api_key": api_key,
                "element_formats": json.dumps(element_formats, ensure_ascii=False),
                "feature_config": json.dumps(feature_config, ensure_ascii=False),
            }

            # 5. Send request
            response = requests.post(url, files=files, data=data, timeout=120)

            if response.status_code != 200:
                error_msg = (
                    f"Somark API Error: {response.status_code} - {response.text}"
                )
                logger.error(error_msg)
                yield self._create_error_log(
                    stage="send_request",
                    message=error_msg,
                    data={"status_code": response.status_code},
                )
                raise RuntimeError(error_msg)

            # 6. Process response
            try:
                result = response.json()
            except json.JSONDecodeError:
                error_msg = f"Invalid JSON response from API. Content: {response.text}"
                yield self._create_error_log(
                    stage="parse_response",
                    message=error_msg,
                )
                raise RuntimeError(error_msg)

            # Extract content
            json_content = ""
            md_content = ""
            error_content = ""

            data_block = result.get("data") if isinstance(result, dict) else None
            result_block = (
                data_block.get("result") if isinstance(data_block, dict) else None
            )
            outputs = (
                result_block.get("outputs") if isinstance(result_block, dict) else None
            )

            if isinstance(result, dict) and result.get("code") == 0:
                if isinstance(outputs, dict):
                    md_value = outputs.get("markdown")
                    if isinstance(md_value, str) and md_value.strip():
                        md_content = md_value

                    json_value = outputs.get("json")
                    if json_value not in (None, "", [], {}):
                        json_content = json.dumps(json_value, ensure_ascii=False)

            else:
                error_content = "Unknown error"
                if isinstance(result, dict):
                    error_content = (
                        (data_block.get("error") if isinstance(data_block, dict) else None)
                        or result.get("message", "Unknown error")
                    )

                logger.error(
                    "SoMark API returned error message: %s", error_content
                )
                error_msg = f"SoMark API returned error message: {error_content}"
                yield self._create_error_log(
                    stage="parse_response",
                    message=error_msg,
                    data={"response_error": error_content},
                )
                raise RuntimeError(error_msg)

            if json_content not in (None, "", [], {}):
                yield self.create_variable_message("json_str", json_content)
            if md_content:
                yield self.create_variable_message("markdown", md_content)

            yield self.create_json_message(result)

        except requests.exceptions.RequestException as e:
            logger.error(f"SoMark Network Error: {str(e)}")
            error_msg = f"Network error connecting to SoMark API: {str(e)}"
            yield self._create_error_log(
                stage="network_request",
                message=error_msg,
            )
            raise RuntimeError(error_msg) from e

        except Exception as e:
            logger.exception("SoMark Plugin Error: %s", str(e))
            raise