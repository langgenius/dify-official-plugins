from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
import httpx
from tools.comfyui_client import ComfyUiClient
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


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
        civitai_api_key = self.runtime.credentials.get("civitai_api_key")
        if civitai_api_key is None:
            raise ToolProviderCredentialValidationError(
                "Please input civitai_api_key")
        self.comfyui = ComfyUiClient(base_url)

        model_id = tool_parameters.get("model_id")
        version_id = tool_parameters.get("version_id")
        save_dir = tool_parameters.get("save_dir")
        try:
            model_data = httpx.get(
                f"https://civitai.com/api/v1/models/{model_id}"
            ).json()

            model_name_human = model_data["name"]
        except:
            raise ToolProviderCredentialValidationError(
                f"Model {model_id} not found.")
        if "error" in model_data:
            raise ToolProviderCredentialValidationError(model_data["error"])
        if version_id is None:
            version_ids = [
                v["id"]
                for v in model_data["modelVersions"]
                if v["availability"] == "Public"
            ]
            version_id = max(version_ids)
        model_detail = None
        for past_model in model_data["modelVersions"]:
            if past_model["id"] == version_id:
                model_detail = past_model
                break
        if model_detail is None:
            raise ToolProviderCredentialValidationError(
                f"Version {version_id} of model {model_name_human} not found."
            )
        model_filenames = [file["name"] for file in model_detail["files"]]

        self.comfyui.download_model(
            f"https://civitai.com/api/download/models/{version_id}",
            save_dir,
            model_filenames[0].split("/")[-1],
            civitai_api_key,
        )
        yield self.create_variable_message("model_name_human", model_name_human)
        yield self.create_variable_message("model_name", model_filenames[0])

        air = ""
        ecosystem, model_type, source = "", "", ""
        try:
            air: str = httpx.get(
                f"https://civitai.com/api/v1/model-versions/{version_id}").json()["air"]
            ecosystem, model_type, source = air.split(":")[2:5]
        except:
            pass
        yield self.create_variable_message("air", air)
        yield self.create_variable_message("ecosystem", ecosystem)
        yield self.create_variable_message("type", model_type)
        yield self.create_variable_message("source", source)
