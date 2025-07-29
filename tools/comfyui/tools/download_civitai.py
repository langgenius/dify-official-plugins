from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.comfyui_client import ComfyUiClient
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.model_manager import ModelManager


class DownloadCivitAI(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url")
        if base_url is None:
            raise ToolProviderCredentialValidationError(
                "Please input base_url")

        self.comfyui = ComfyUiClient(base_url)
        self.model_manager = ModelManager(
            self.comfyui,
            civitai_api_key=self.runtime.credentials.get("civitai_api_key"),
            hf_api_key=None,
        )

        model_id = tool_parameters.get("model_id")
        version_id = tool_parameters.get("version_id")
        save_dir = tool_parameters.get("save_dir")
        if version_id is None:
            version_id = max(self.model_manager.fetch_version_ids(model_id))
        model_name_human, model_filenames = self.model_manager.download_civitai(
            model_id, version_id, save_dir
        )
        yield self.create_variable_message("model_name_human", model_name_human)
        yield self.create_variable_message("model_name", model_filenames[0])

        ecosystem, model_type, source, id = self.model_manager.fetch_civitai_air(
            version_id
        )
        yield self.create_variable_message(
            "air", f"urn:air:{ecosystem}:{model_type}:{source}:{id}"
        )
        yield self.create_variable_message("ecosystem", ecosystem)
        yield self.create_variable_message("type", model_type)
        yield self.create_variable_message("source", source)
