from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.document_parsing import DocumentParsingTool
from tools.document_parsing_vl import DocumentParsingVlTool
from tools.text_recognition import TextRecognitionTool


class PaddleocrProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if "aistudio_access_token" not in credentials:
            raise ToolProviderCredentialValidationError(
                "AI Studio access token must be provided"
            )

        api_url_keys = (
            "text_recognition_api_url",
            "document_parsing_api_url",
            "document_parsing_vl_api_url",
        )
        tool_classes = (
            TextRecognitionTool,
            DocumentParsingTool,
            DocumentParsingVlTool,
        )
        test_file = "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/general_ocr_002.png"

        if not any(key in credentials for key in api_url_keys):
            raise ToolProviderCredentialValidationError(
                "You should provide at least one API URL"
            )

        for api_url_key, tool_cls in zip(api_url_keys, tool_classes):
            if api_url_key in credentials:
                try:
                    self._test_tool_validation(tool_cls, credentials, test_file)
                except Exception as e:
                    raise ToolProviderCredentialValidationError(
                        f"Invalid credentials for {tool_cls.__name__}"
                    ) from e

    def _test_tool_validation(
        self, tool_cls, credentials: dict[str, Any], test_file: str
    ) -> None:
        tool = tool_cls.from_credentials(credentials)

        for _ in tool.invoke(tool_parameters={"file": test_file}):
            break
