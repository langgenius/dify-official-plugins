from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.paddleocr_text_recognition import PaddleocrTextRecognitionTool


class PaddleocrTextRecognitionProvider(ToolProvider):

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in PaddleocrTextRecognitionTool.from_credentials(credentials).invoke(
                tool_parameters={
                    "file": "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/general_ocr_002.png"
                }
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
