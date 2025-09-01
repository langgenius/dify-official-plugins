import os
import re

import requests

from tools.comfyui_workflow import ComfyUiWorkflow
from tools.comfyui_client import ComfyUiClient


class ModelManager:
    def __init__(
        self,
        comfyui_cli: ComfyUiClient,
        civitai_api_key: str | None,
        hf_api_key: str | None,
    ):
        self._comfyui_cli = comfyui_cli
        self._civitai_api_key = civitai_api_key
        self._hf_api_key = hf_api_key

    def get_civitai_api_key(self):
        if self._civitai_api_key is None:
            raise Exception("Please input CivitAI API Key")
        return self._civitai_api_key

    def get_hf_api_key(self):
        if self._hf_api_key is None:
            raise Exception("Please input HuggingFace API Key")
        return self._hf_api_key

    def decode_lora(self, lora_info: str, save_dir: str = "loras"):
        # lora_info can be expressed as ([A-Za-z0-9\.]+|(civitai:[0-9]+(@[0-9]+)?))(:[0-9]+(\.[0-9])?)? in regular expression.
        # For example, if lora_info = "lora.safetensor:0.8", it means a local model "lora.safetensor" should be applied with its strength 0.8
        # If lora_info = "civitai:5529", it means a CivitAI model https://civitai.com/models/5529/eye-lora should be applied with its strength 1.0(default value).
        lora_info = lora_info.lstrip(" ").rstrip(" ")
        if not re.match("([A-Za-z0-9\.]+|(civitai:[0-9]+(@[0-9]+)?))(:[0-9]+(\.[0-9])?)?", lora_info):
            raise Exception(f"Invalid lora_info")

        if len(lora_info.split(":")) == 3 or (lora_info.split(":")[0] != "civitai" and len(lora_info.split(":")) == 2):
            lora_name = self.decode_model_name(
                ":".join(lora_info.split(":")[:-1]), save_dir)
            lora_strength = float(lora_info.split(":")[-1])
        else:
            lora_name = self.decode_model_name(lora_info, save_dir)
            lora_strength = 1.0
        return lora_name, lora_strength

    def decode_model_name(
        self,
        model_name: str,
        save_dir: str,
    ) -> str:
        # model_name can be expressed as [A-Za-z0-9\.]+|(civitai:[0-9]+(@[0-9]+)?) in regular expression.
        # For example, if model_name = "lora.safetensor", it means a local model "lora.safetensor"
        # If model_name = "civitai:5529", it means a CivitAI model https://civitai.com/models/5529/eye-lora
        model_name = model_name.lstrip(" ").rstrip(" ")
        if not re.match("[A-Za-z0-9\.]+|(civitai:[0-9]+(@[0-9]+)?)", model_name):
            raise Exception(f"Invalid model_name")
        if len(save_dir) == 0:
            raise Exception(f"Please specify save_dir")
        if model_name in self._comfyui_cli.get_model_dirs(save_dir):
            # model_name is the name for an existing model in ComfyUI
            return model_name
        civit_patterns = re.findall("^(civitai: *)?([0-9]+)(@([0-9]+))?", model_name)
        if len(civit_patterns) > 0:
            # model_name is CivitAI's AIR
            civit_pattern = civit_patterns[0]
            try:
                model_id = int(civit_pattern[1])
            except:
                raise Exception(f"CivitAI model {model_name} does not exist")
            try:
                version_id = int(civit_pattern[3])
            except:
                version_id = None
            model_name_human, filenames = self.download_civitai(
                model_id, version_id, save_dir
            )
            return filenames[0]
        if len(re.findall("https?://huggingface\.co/.*", model_name)) > 0:
            # model_name is a URL for huggingface.co
            url = model_name
            return self.download_model(
                url, save_dir, model_name.split("/")[-1], self.get_hf_api_key()
            )
        if len(re.findall("https?://.*", model_name)) > 0:
            # model_name is a general URL
            url = model_name
            return self.download_model(url, save_dir, model_name.split("/")[-1], None)
        raise Exception(
            f"Model {model_name} does not exist in the local folder {save_dir}/ or online."
        )

    def download_model(self, url: str, save_dir: str, filename: str | None = None, token=None) -> str:
        headers = {}
        if token is not None:
            headers = {"Authorization": f"Bearer {token}"}
        response = requests.head(url, headers=headers)
        if response.status_code == 401:
            raise Exception(f"401 Unauthorized. Please check the api_token.")
        elif response.status_code >= 400:
            raise Exception(
                f"Download failed. Error {response.status_code}. Please check the URL."
            )

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "download.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        if filename is None:
            filename = url.split("/")[-1].split("?")[0]
        if token is None:
            token = ""
        workflow.set_asset_downloader(None, url, save_dir, filename, token)

        try:
            _ = self._comfyui_cli.generate(workflow.json())
        except Exception as e:
            error = f"Failed to download: {str(e)}."
            if len(self._comfyui_cli.get_model_dirs(save_dir)) == 0:
                error += f"Please make sure that https://github.com/ServiceStack/comfy-asset-downloader works on ComfyUI and the destination folder named models/{save_dir} exists."
            else:
                error += "Please make sure that https://github.com/ServiceStack/comfy-asset-downloader works on ComfyUI."
            raise Exception(error)

        return filename

    def fetch_version_ids(self, model_id: int):
        try:
            model_data = requests.get(
                f"https://civitai.com/api/v1/models/{model_id}"
            ).json()
        except:
            raise Exception(f"Model {model_id} not found.")
        version_ids = [
            v["id"]
            for v in model_data["modelVersions"]
            if v["availability"] == "Public"
        ]
        return version_ids

    def download_civitai(self, model_id: int, version_id: int, save_dir: str) -> tuple[str, list[str]]:
        try:
            model_data = requests.get(
                f"https://civitai.com/api/v1/models/{model_id}"
            ).json()

            model_name_human = model_data["name"]
        except:
            raise Exception(f"Model {model_id} not found.")
        if "error" in model_data:
            raise Exception(model_data["error"])
        if version_id is None:
            version_id = max(self.fetch_version_ids(model_id))
        model_detail = None
        for past_model in model_data["modelVersions"]:
            if past_model["id"] == version_id:
                model_detail = past_model
                break
        if model_detail is None:
            raise Exception(
                f"Version {version_id} of model {model_name_human} not found."
            )
        model_filenames = [file["name"] for file in model_detail["files"]]

        self.download_model(
            f"https://civitai.com/api/download/models/{version_id}",
            save_dir,
            model_filenames[0].split("/")[-1],
            self.get_civitai_api_key(),
        )

        return model_name_human, model_filenames

    def download_hugging_face(self, repo_id: str, filepath: str, save_dir: str):
        self.download_model(
            f"https://huggingface.co/{repo_id}/resolve/main/{filepath}",
            save_dir,
            filepath.split("/")[-1],
            self.get_hf_api_key(),
        )
        return filepath.split("/")[-1]

    def fetch_civitai_air(self, version_id: int) -> tuple[str, str, str, str]:
        try:
            air_str: str = requests.get(
                f"https://civitai.com/api/v1/model-versions/{version_id}"
            ).json()["air"]
            urn, air, ecosystem, model_type, source, id = air_str.split(":")
            return ecosystem, model_type, source, id
        except:
            return "", "", "", ""

    def download_from_json(self, workflow_json: str) -> list[str]:
        workflow = ComfyUiWorkflow(workflow_json)
        models = []
        for node in workflow.json_original()["nodes"]:
            if "properties" in node and "models" in node["properties"]:
                models += node["properties"]["models"]

        for model in models:
            token = None
            if "://civitai.com" in model["url"]:
                token = self.get_civitai_api_key()
            elif "://huggingface.co" in model["url"]:
                token = self.get_hf_api_key()

            self.download_model(model["url"], model["directory"], model["name"], token)
        model_names = [m["name"] for m in models]
        return model_names
