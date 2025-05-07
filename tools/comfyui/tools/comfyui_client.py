from enum import StrEnum
import json
import random
import uuid

import httpx
import requests
from websocket import WebSocket
from yarl import URL


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


class ComfyUiClient:
    def __init__(self, base_url: str):
        self.base_url = URL(base_url)

    def get_checkpoints(self) -> list[str]:
        """
        get checkpoints
        """
        try:
            api_url = str(self.base_url / "models" / "checkpoints")
            response = httpx.get(url=api_url, timeout=(2, 10))
            if response.status_code != 200:
                return []
            else:
                return response.json()
        except Exception as e:
            return []

    def get_loras(self) -> list[str]:
        """
        get loras
        """
        try:
            base_url = self.runtime.credentials.get("base_url", None)
            if not base_url:
                return []
            api_url = str(URL(base_url) / "models" / "loras")
            response = httpx.get(url=api_url, timeout=(2, 10))
            if response.status_code != 200:
                return []
            else:
                return response.json()
        except Exception as e:
            return []

    def get_samplers(self) -> list[str]:
        """
        get samplers
        """
        try:
            api_url = str(self.base_url / "object_info" / "KSampler")
            response = httpx.get(url=api_url, timeout=(2, 10))
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
            response = httpx.get(url=api_url, timeout=(2, 10))
            if response.status_code != 200:
                return []
            else:
                data = response.json()["KSampler"]["input"]["required"]
                return data["scheduler"][0]
        except Exception as e:
            return []

    def get_history(self, prompt_id: str) -> dict:
        res = httpx.get(str(self.base_url / "history"), params={"prompt_id": prompt_id})
        history = res.json()[prompt_id]
        return history

    def get_image(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        response = httpx.get(
            str(self.base_url / "view"),
            params={"filename": filename, "subfolder": subfolder, "type": folder_type},
        )
        return response.content

    def post_image(
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
            res = requests.post(str(self.base_url / "upload" / "image"), files=files)
            image_name = res.json().get("name")
            return image_name
        except:
            return None

    def queue_prompt(self, client_id: str, prompt: dict) -> str:
        res = httpx.post(
            str(self.base_url / "prompt"),
            json={"client_id": client_id, "prompt": prompt},
        )
        prompt_id = res.json()["prompt_id"]
        return prompt_id

    def open_websocket_connection(self) -> tuple[WebSocket, str]:
        client_id = str(uuid.uuid4())
        ws = WebSocket()
        ws_protocol = "ws"
        if self.base_url.scheme == "https":
            ws_protocol = "wss"
        ws_address = (
            f"{ws_protocol}://{self.base_url.authority}/ws?clientId={client_id}"
        )
        ws.connect(ws_address)
        return ws, client_id

    def set_prompt_by_ksampler(
        self, origin_prompt: dict, positive_prompt: str, negative_prompt: str = ""
    ) -> dict:
        prompt = origin_prompt.copy()
        id_to_class_type = {id: details["class_type"] for id, details in prompt.items()}
        k_sampler = [
            key for key, value in id_to_class_type.items() if value == "KSampler"
        ][0]
        positive_input_id = prompt.get(k_sampler)["inputs"]["positive"][0]
        prompt.get(positive_input_id)["inputs"]["text"] = positive_prompt

        if negative_prompt != "":
            negative_input_id = prompt.get(k_sampler)["inputs"]["negative"][0]
            prompt.get(negative_input_id)["inputs"]["text"] = negative_prompt

        return prompt

    def set_prompt_images_by_ids(
        self, origin_prompt: dict, image_names: list[str], image_ids: list[str]
    ) -> dict:
        prompt = origin_prompt.copy()
        for index, image_node_id in enumerate(image_ids):
            prompt[image_node_id]["inputs"]["image"] = image_names[index]
        return prompt

    def set_prompt_images_by_default(
        self, origin_prompt: dict, image_names: list[str]
    ) -> dict:
        prompt = origin_prompt.copy()
        id_to_class_type = {id: details["class_type"] for id, details in prompt.items()}
        load_image_nodes = [
            key for key, value in id_to_class_type.items() if value == "LoadImage"
        ]
        for load_image, image_name in zip(load_image_nodes, image_names):
            prompt.get(load_image)["inputs"]["image"] = image_name
        return prompt

    def set_prompt_seed_by_id(self, origin_prompt: dict, seed_id: str) -> dict:
        prompt = origin_prompt.copy()
        if seed_id not in prompt:
            raise Exception("Not a valid seed node")
        if "seed" in prompt[seed_id]["inputs"]:
            prompt[seed_id]["inputs"]["seed"] = random.randint(10**14, 10**15 - 1)
        elif "noise_seed" in prompt[seed_id]["inputs"]:
            prompt[seed_id]["inputs"]["noise_seed"] = random.randint(10**14, 10**15 - 1)
        else:
            raise Exception("Not a valid seed node")
        return prompt

    def track_progress(self, prompt: dict, ws: WebSocket, prompt_id: str):
        node_ids = list(prompt.keys())
        finished_nodes = []

        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message["type"] == "progress":
                    data = message["data"]
                    current_step = data["value"]
                    print("In K-Sampler -> Step: ", current_step, " of: ", data["max"])
                if message["type"] == "execution_cached":
                    data = message["data"]
                    for itm in data["nodes"]:
                        if itm not in finished_nodes:
                            finished_nodes.append(itm)
                            print(
                                "Progress: ",
                                len(finished_nodes),
                                "/",
                                len(node_ids),
                                " Tasks done",
                            )
                if message["type"] == "executing":
                    data = message["data"]
                    if data["node"] not in finished_nodes:
                        finished_nodes.append(data["node"])
                        print(
                            "Progress: ",
                            len(finished_nodes),
                            "/",
                            len(node_ids),
                            " Tasks done",
                        )

                    if data["node"] is None and data["prompt_id"] == prompt_id:
                        break  # Execution is done
            else:
                continue

    def download_image(self, filename, subfolder, folder_type):
        """
        download image
        """
        url = str(self.base_url / "view")
        response = httpx.get(
            url,
            params={"filename": filename, "subfolder": subfolder, "type": folder_type},
            timeout=(2, 10),
        )
        return response.content

    def generate_image_by_prompt(self, prompt: dict) -> list[dict[str, str | bytes]]:
        try:
            ws, client_id = self.open_websocket_connection()
            prompt_id = self.queue_prompt(client_id, prompt)
            self.track_progress(prompt, ws, prompt_id)
            history = self.get_history(prompt_id)
            images = []
            for output in history["outputs"].values():
                for img in output.get("images", []):
                    image_data = self.get_image(
                        img["filename"], img["subfolder"], img["type"]
                    )
                    images.append(
                        {
                            "data": image_data,
                            "filename": img["filename"],
                            "type": img["type"],
                        }
                    )
            return images
        finally:
            ws.close()

    def queue_prompt_image(self, client_id, prompt):
        """
        send prompt task and rotate
        """
        url = str(self.base_url / "prompt")
        respond = httpx.post(
            url,
            data=json.dumps({"client_id": client_id, "prompt": prompt}),
            timeout=(2, 10),
        )
        prompt_id = respond.json()["prompt_id"]
        ws = WebSocket()
        if "https" == self.base_url.scheme:
            ws_url = str(self.base_url).replace("https", "ws")
        else:
            ws_url = str(self.base_url).replace("http", "ws")
        ws.connect(str(URL(f"{ws_url}") / "ws") + f"?clientId={client_id}", timeout=120)
        output_images = {}
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message["type"] == "executing":
                    data = message["data"]
                    if data["node"] is None and data["prompt_id"] == prompt_id:
                        break
                elif message["type"] == "status":
                    data = message["data"]
                    if data["status"]["exec_info"]["queue_remaining"] == 0 and data.get(
                        "sid"
                    ):
                        break
            else:
                continue
        history = self.get_history(prompt_id)
        for o in history["outputs"]:
            for node_id in history["outputs"]:
                node_output = history["outputs"][node_id]
                if "images" in node_output:
                    images_output = []
                    for image in node_output["images"]:
                        image_data = self.download_image(
                            image["filename"],
                            image["subfolder"],
                            image["type"],
                        )
                        images_output.append(image_data)
                    output_images[node_id] = images_output
        ws.close()
        return output_images
