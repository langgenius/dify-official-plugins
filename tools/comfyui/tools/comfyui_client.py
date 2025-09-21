import dataclasses
import json
import mimetypes
import os
import uuid
from enum import StrEnum

import requests
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from websocket import WebSocket
from yarl import URL

from tools.comfyui_workflow import ComfyUiWorkflow


class FileType(StrEnum):
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    CUSTOM = "custom"

    @staticmethod
    def value_of(value):
        for member in FileType:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")


@dataclasses.dataclass
class ComfyUiResultFile:
    blob: bytes
    filename: str
    mime_type: str
    type: str


class ComfyUiClient:
    def __init__(self, base_url: str, api_key: str | None = None, api_key_comfy_org: str = ""):  # Add api_key parameter
        if base_url is None or len(base_url) == 0:
            raise Exception("Please input base_url")
        self.base_url = URL(base_url)
        self.api_key = api_key  # Store api_key
        # https://docs.comfy.org/development/comfyui-server/api-key-integration#integration-of-api-key-to-use-comfyui-api-nodes
        self.api_key_comfy_org = api_key_comfy_org

    def _get_headers(self) -> dict:  # Helper method to get headers
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get_model_dirs(self, path: str | None = None) -> list[str]:
        """
        get checkpoints
        """
        try:
            if path is None:
                api_url = str(self.base_url / "models")
            else:
                api_url = str(self.base_url / "models" / path)
            response = requests.get(url=api_url, timeout=(2, 10), headers=self._get_headers())  # Add headers
            if response.status_code != 200:
                return []
            else:
                return response.json()
        except Exception as e:
            return []

    def get_all_models(self, exclude_dirs: list[str] = ["custom_nodes"]) -> list[str]:
        result = []
        for model_dir in self.get_model_dirs():
            if model_dir in exclude_dirs:
                continue
            for model_name in self.get_model_dirs(model_dir):
                result.append(f"{model_dir}/{model_name}")
        return result

    def get_checkpoints(self) -> list[str]:
        """
        get checkpoints
        """
        return self.get_model_dirs("checkpoints")

    def get_loras(self) -> list[str]:
        """
        get loras
        """
        return self.get_model_dirs("loras")

    def get_samplers(self) -> list[str]:
        """
        get samplers
        """
        try:
            api_url = str(self.base_url / "object_info" / "KSampler")
            response = requests.get(url=api_url, timeout=(2, 10), headers=self._get_headers())  # Add headers
            if response.status_code != 200:
                return []
            else:
                data = response.json()["KSampler"]["input"]["required"]
                return data["sampler_name"][0]
        except Exception as e:
            return []

    def get_schedulers(self) -> list[str]:
        """
        get schedulers
        """
        try:
            api_url = str(self.base_url / "object_info" / "KSampler")
            response = requests.get(url=api_url, timeout=(2, 10), headers=self._get_headers())  # Add headers
            if response.status_code != 200:
                return []
            else:
                data = response.json()["KSampler"]["input"]["required"]
                return data["scheduler"][0]
        except Exception as e:
            return []

    def get_history(self, prompt_id: str) -> dict:
        res = requests.get(
            str(self.base_url / "history"),
            params={"prompt_id": prompt_id},
            headers=self._get_headers(),
        )  # Add headers
        history = res.json()[prompt_id]
        return history

    def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        response = requests.get(
            str(self.base_url / "view"),
            params={"filename": filename, "subfolder": subfolder, "type": folder_type},
            headers=self._get_headers(),  # Add headers
        )
        return response.content

    def upload_image(
        self,
        filename: str,
        fileblob: bytes,
        mime_type: str,
    ) -> str | None:
        files = {
            "image": (filename, fileblob, mime_type),
            "overwrite": "true",
        }
        try:
            res = requests.post(
                # Add headers for requests
                str(self.base_url / "upload" / "image"),
                files=files,
                headers=self._get_headers(),
            )
            image_name = res.json().get("name")
            return image_name
        except:
            return None

    def queue_prompt(self, client_id: str, prompt: dict) -> str:
        res = requests.post(
            str(self.base_url / "prompt"),
            data=json.dumps(
                {
                    "client_id": client_id,
                    "prompt": prompt,
                    "extra_data": {"api_key_comfy_org": self.api_key_comfy_org},
                }
            ),
            headers=self._get_headers(),  # Add headers
        )
        if "error" in res.json():
            raise Exception("ComfyUI error: " + json.dumps(res.json()))
        try:
            prompt_id = res.json()["prompt_id"]
        except:
            raise Exception("Error queuing the prompt. Please check the workflow JSON.")
        return prompt_id

    def open_websocket_connection(self) -> tuple[WebSocket, str]:
        client_id = str(uuid.uuid4())
        ws = WebSocket()
        ws_protocol = "ws"
        if self.base_url.scheme == "https":
            ws_protocol = "wss"
        ws_address = f"{ws_protocol}://{self.base_url.authority}/ws?clientId={client_id}"
        headers = []
        if self.api_key:
            headers.append(f"Authorization: Bearer {self.api_key}")
        ws.connect(ws_address, header=headers)
        return ws, client_id

    def wait_until_generation(self, prompt: dict, ws: WebSocket, prompt_id: str):
        node_ids = list(prompt.keys())
        finished_nodes = []

        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message["type"] == "progress":
                    data = message["data"]
                    current_step = data["value"]
                if message["type"] == "execution_cached":
                    data = message["data"]
                    for itm in data["nodes"]:
                        if itm not in finished_nodes:
                            finished_nodes.append(itm)
                if message["type"] == "executing":
                    data = message["data"]
                    if data["node"] not in finished_nodes:
                        finished_nodes.append(data["node"])
                    if data["node"] is None and data["prompt_id"] == prompt_id:
                        break  # Execution is done

    def generate(self, workflow_json: dict) -> list[ComfyUiResultFile]:
        try:
            ws, client_id = self.open_websocket_connection()
        except Exception as e:
            raise Exception("Failed to open websocket:" + str(e))
        try:
            prompt_id = self.queue_prompt(client_id, workflow_json)
            self.wait_until_generation(workflow_json, ws, prompt_id)
        except Exception as e:
            raise Exception("Error occured during image generation:" + str(e))
        ws.close()

        history = self.get_history(prompt_id)
        files: list[ComfyUiResultFile] = []
        for output in history["outputs"].values():
            for file in output.get("images", []) + output.get("gifs", []) + output.get("audio", []):
                image_data = self.get_image(file["filename"], file["subfolder"], file["type"])
                generated_img = ComfyUiResultFile(
                    blob=image_data,
                    filename=file["filename"],
                    mime_type=mimetypes.guess_type(file["filename"])[0],
                    type=file["type"],
                )
                files.append(generated_img)

        return files

    def convert_webp2mp4(self, webp_blob: bytes, fps: int):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "webp2mp4.json")) as file:
            workflow = ComfyUiWorkflow(file.read())

        uploaded_image = self.upload_image("input.webp", webp_blob, "image/webp")
        workflow.set_property("25", "inputs/frame_rate", fps)
        workflow.set_image_names([uploaded_image])

        try:
            output_files = self.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to download: {str(e)}. "
                + "Please make sure https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite works on ComfyUI"
            )
        return output_files[0]
