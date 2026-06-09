from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.document_parsing import DocumentParsingTool
from tools.document_parsing_vl import DocumentParsingVlTool
from tools.text_recognition import TextRecognitionTool
from tools.utils import call_paddleocr_api, get_api_client_config


class PaddleocrProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if "aistudio_access_token" not in credentials:
            raise ToolProviderCredentialValidationError(
                "AI Studio access token must be provided"
            )

        # Get base_url (optional, uses SDK default if not provided)
        base_url = credentials.get("base_url")

        # Test with OCR (works for all models)
        test_file = "https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/general_ocr_002.png"

        try:
            client_config = get_api_client_config(
                access_token=credentials["aistudio_access_token"],
                base_url=base_url,
            )
            call_paddleocr_api(
                model="PP-OCRv5",
                file_url=test_file,
                file_path=None,
                options={},
                client_config=client_config,
                is_document_parsing=False,
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Validation failed: {e}"
            ) from e