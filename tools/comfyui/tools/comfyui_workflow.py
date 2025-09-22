import dataclasses
import json
import os
import secrets
from copy import deepcopy
from typing import Optional

LORA_NODE = {
    "inputs": {
        "lora_name": "",
        "strength_model": 1,
        "strength_clip": 1,
        "model": ["11", 0],
        "clip": ["11", 1],
    },
    "class_type": "LoraLoader",
    "_meta": {"title": "Load LoRA"},
}

FluxGuidanceNode = {
    "inputs": {"guidance": 3.5, "conditioning": ["6", 0]},
    "class_type": "FluxGuidance",
    "_meta": {"title": "FluxGuidance"},
}


@dataclasses.dataclass
class ComfyUIModel:
    name: str
    url: str
    directory: str


class ComfyUiWorkflow:
    def __init__(self, workflow_json: str | dict):
        if type(workflow_json) is str:

            def clean_json_string(string: str) -> str:
                for char in ["\n", "\r", "\t", "\x08", "\x0c"]:
                    string = string.replace(char, "")
                for char_id in range(0x007F, 0x00A1):
                    string = string.replace(chr(char_id), "")
                return string

            workflow_json: dict = json.loads(clean_json_string(workflow_json))
        elif type(workflow_json) is dict:
            pass
        else:
            raise Exception("workflow_json has unsupported format. Please convert it to str or dict")

        self._workflow_original = workflow_json
        self.models_to_download: list[ComfyUIModel] = []
        if "nodes" in workflow_json:
            try:
                self._workflow_api = self.convert_to_api_ready(workflow_json)
            except Exception as e:
                raise Exception(f"Failed to convert Workflow to API ready. {str(e)}")
            for node in workflow_json["nodes"]:
                if "properties" in node and "models" in node["properties"]:
                    for model in node["properties"]["models"]:
                        self.models_to_download.append(ComfyUIModel(model["name"], model["url"], model["directory"]))
        else:
            self._workflow_api = deepcopy(workflow_json)

    def __str__(self):
        return json.dumps(self._workflow_api)

    def convert_to_api_ready(self, workflow_json: dict) -> dict:
        result = {}
        current_dir = os.path.dirname(os.path.realpath(__file__))
        widgets_value_path = os.path.join(current_dir, "json", "widgets_value_names.json")
        with open(widgets_value_path, encoding="UTF-8") as f:
            widgets_value_names = json.loads(f.read())
        nodes = workflow_json["nodes"]
        links = workflow_json["links"]
        for node in nodes:
            if node["mode"] == 4:  # Disabled node
                continue
            inputs = {}
            class_type = node["type"]
            if class_type in ["MarkdownNote"]:
                continue
            # Set input values
            if class_type in widgets_value_names:
                for i, value_name in enumerate(widgets_value_names[class_type]):
                    inputs[value_name] = node["widgets_values"][i]
            elif class_type in ["Note"]:
                continue
            else:
                raise Exception(f"{class_type} not found in widgets_value_names.")

            # Set links
            for input in node["inputs"]:
                link_id = input["link"]
                link = None
                for li in links:
                    if li[0] == link_id:
                        link = li
                        break
                if link is None:
                    continue
                link_id, source_id, port_idx, _, _, type = link
                inputs[input["name"]] = [str(source_id), port_idx]
            result[str(node["id"])] = {
                "class_type": class_type,
                "_meta": {"title": "TITLE"},
                "inputs": inputs,
            }
        result = {key: result[key] for key in sorted(result, key=lambda k: int(k))}
        return result

    def json(self) -> dict:
        return self._workflow_api

    def json_str(self) -> str:
        return json.dumps(self._workflow_api)

    def json_original(self) -> dict:
        return self._workflow_original

    def json_original_str(self) -> str:
        return json.dumps(self._workflow_original)

    def get_models_to_download(self) -> list[ComfyUIModel]:
        return self.models_to_download

    def get_property(self, node_id: str | None, path: str):
        try:
            workflow_json = self._workflow_api[node_id]
            for name in path.split("/")[:-1]:
                workflow_json = workflow_json[name]
            return workflow_json[path.split("/")[-1]]
        except:
            return None

    def set_property(self, node_id: str | None, path: str, value, can_create=False):
        workflow_json = self._workflow_api[node_id]
        for name in path.split("/")[:-1]:
            if not can_create and name not in workflow_json:
                raise Exception("Cannot create a new property.")
            workflow_json = workflow_json[name]
        workflow_json[path.split("/")[-1]] = value

    def get_class_type(self, node_id):
        return self.get_property(node_id, "class_type")

    def get_node_ids_by_class_type(self, class_type: str) -> list[str]:
        node_ids = []
        for node_id in self._workflow_api:
            if self.get_class_type(node_id) == class_type:
                node_ids.append(node_id)
        return node_ids

    def identify_node_by_class_type(self, class_type: str) -> str:
        # Returns the node_id of the only node with a given class_type
        possible_node_ids = self.get_node_ids_by_class_type(class_type)
        if len(possible_node_ids) == 0:
            raise Exception(f"There are no nodes with the class_name '{class_type}'.")
        elif len(possible_node_ids) > 1:
            raise Exception(f"There are some nodes with the class_name '{class_type}'.")
        return possible_node_ids[0]

    def randomize_seed(self):
        for node_id in self._workflow_api:
            if self.get_property(node_id, "inputs/seed") is not None:
                self.set_property(node_id, "inputs/seed", secrets.randbelow(10**8))
            if self.get_property(node_id, "inputs/noise_seed") is not None:
                self.set_property(node_id, "inputs/noise_seed", secrets.randbelow(10**8))

    def set_image_names(self, image_names: list[str], ordered_node_ids: Optional[list[str]] = None):
        if ordered_node_ids is None:
            ordered_node_ids = self.get_node_ids_by_class_type("LoadImage")
        for i, node_id in enumerate(ordered_node_ids):
            self.set_property(node_id, "inputs/image", image_names[i])

    def set_model_loader(self, node_id: str | None, ckpt_name: str):
        if node_id is None:
            node_id = self.identify_node_by_class_type("CheckpointLoaderSimple")
        if self.get_property(node_id, "class_type") != "CheckpointLoaderSimple":
            raise Exception(f"Node {node_id} is not CheckpointLoaderSimple")
        self.set_property(node_id, "inputs/ckpt_name", ckpt_name)

    def set_k_sampler(
        self,
        node_id: str | None,
        steps: int,
        sampler_name: str,
        scheduler_name: str,
        cfg: float,
        denoise: float,
        seed: int | None = None,
    ):
        if node_id is None:
            node_id = self.identify_node_by_class_type("KSampler")
        if self.get_class_type(node_id) != "KSampler":
            raise Exception(f"Node {node_id} is not KSampler")
        self.set_property(node_id, "inputs/steps", steps)
        self.set_property(node_id, "inputs/sampler_name", sampler_name)
        self.set_property(node_id, "inputs/scheduler", scheduler_name)
        self.set_property(node_id, "inputs/cfg", cfg)
        self.set_property(node_id, "inputs/denoise", denoise)
        if seed is None:
            seed = secrets.randbelow(100000000)
        self.set_property(node_id, "inputs/seed", seed)

    def set_sd3_latent_image(
        self,
        node_id: str | None,
        width: int,
        height: int,
        batch_size: int = 1,
    ):
        if node_id is None:
            node_id = self.identify_node_by_class_type("EmptySD3LatentImage")
        if self.get_class_type(node_id) != "EmptySD3LatentImage":
            raise Exception(f"Node {node_id} is not EmptySD3LatentImage")
        self.set_property(node_id, "inputs/width", width)
        self.set_property(node_id, "inputs/height", height)
        self.set_property(node_id, "inputs/batch_size", batch_size)

    def set_empty_latent_image(
        self,
        node_id: str | None,
        width: int,
        height: int,
        batch_size: int = 1,
    ):
        if node_id is None:
            node_id = self.identify_node_by_class_type("EmptyLatentImage")
        if self.get_class_type(node_id) != "EmptyLatentImage":
            raise Exception(f"Node {node_id} is not EmptyLatentImage")
        self.set_property(node_id, "inputs/width", width)
        self.set_property(node_id, "inputs/height", height)
        self.set_property(node_id, "inputs/batch_size", batch_size)

    def set_prompt(self, node_id: str | None, prompt: str):
        if node_id is None:
            node_id = self.identify_node_by_class_type("CLIPTextEncode")
        if self.get_class_type(node_id) != "CLIPTextEncode":
            raise Exception(f"Node {node_id} is not CLIPTextEncode")
        self.set_property(node_id, "inputs/text", prompt)

    def set_clip(self, node_id: str | None, clip_name: str):
        if node_id is None:
            node_id = self.identify_node_by_class_type("CLIPLoader")
        if self.get_class_type(node_id) != "CLIPLoader":
            raise Exception(f"Node {node_id} is not CLIPLoader")
        self.set_property(node_id, "inputs/clip_name", clip_name)

    def set_clip_vision(self, node_id: str | None, clip_name: str):
        if node_id is None:
            node_id = self.identify_node_by_class_type("CLIPVisionLoader")
        if self.get_class_type(node_id) != "CLIPVisionLoader":
            raise Exception(f"Node {node_id} is not CLIPVisionLoader")
        self.set_property(node_id, "inputs/clip_name", clip_name)

    def set_dual_clip(self, node_id: str | None, clip_name1: str, clip_name2: str):
        if node_id is None:
            node_id = self.identify_node_by_class_type("DualCLIPLoader")
        if self.get_class_type(node_id) != "DualCLIPLoader":
            raise Exception(f"Node {node_id} is not DualCLIPLoader")
        self.set_property(node_id, "inputs/clip_name1", clip_name1)
        self.set_property(node_id, "inputs/clip_name2", clip_name2)

    def set_vae(self, node_id: str | None, vae_name: str):
        if node_id is None:
            node_id = self.identify_node_by_class_type("VAELoader")
        if self.get_class_type(node_id) != "VAELoader":
            raise Exception(f"Node {node_id} is not VAELoader")
        self.set_property(node_id, "inputs/vae_name", vae_name)

    def set_unet(self, node_id: str | None, unet_name: str):
        if node_id is None:
            node_id = self.identify_node_by_class_type("UNETLoader")
        if self.get_class_type(node_id) != "UNETLoader":
            raise Exception(f"Node {node_id} is not UNETLoader")
        self.set_property(node_id, "inputs/unet_name", unet_name)

    def set_empty_hunyuan(
        self,
        node_id: str | None,
        width: int,
        height: int,
        length: int,
        batch_size: int = 1,
    ):
        if node_id is None:
            node_id = self.identify_node_by_class_type("EmptyHunyuanLatentVideo")
        if self.get_class_type(node_id) != "EmptyHunyuanLatentVideo":
            raise Exception(f"Node {node_id} is not EmptyHunyuanLatentVideo")
        self.set_property(node_id, "inputs/width", width)
        self.set_property(node_id, "inputs/height", height)
        self.set_property(node_id, "inputs/length", length)
        self.set_property(node_id, "inputs/batch_size", batch_size)

    def set_empty_mochi(
        self,
        node_id: str | None,
        width: int,
        height: int,
        length: int,
        batch_size: int = 1,
    ):
        if node_id is None:
            node_id = self.identify_node_by_class_type("EmptyMochiLatentVideo")
        if self.get_class_type(node_id) != "EmptyMochiLatentVideo":
            raise Exception(f"Node {node_id} is not EmptyMochiLatentVideo")
        self.set_property(node_id, "inputs/width", width)
        self.set_property(node_id, "inputs/height", height)
        self.set_property(node_id, "inputs/length", length)
        self.set_property(node_id, "inputs/batch_size", batch_size)

    def set_animated_webp(self, node_id: str | None, fps: int, lossless: bool = True):
        if node_id is None:
            node_id = self.identify_node_by_class_type("SaveAnimatedWEBP")
        if self.get_class_type(node_id) != "SaveAnimatedWEBP":
            raise Exception(f"Node {node_id} is not SaveAnimatedWEBP")
        self.set_property(node_id, "inputs/fps", fps)
        self.set_property(node_id, "inputs/lossless", "true" if lossless else "false")

    def set_asset_downloader(self, node_id: str | None, url: str, save_to: str, filename: str, token: str):
        # This node is downloadable from https://github.com/ServiceStack/comfy-asset-downloader.
        if node_id is None:
            node_id = self.identify_node_by_class_type("AssetDownloader")
        if self.get_class_type(node_id) != "AssetDownloader":
            raise Exception(f"Node {node_id} is not AssetDownloader")
        self.set_property(node_id, "inputs/url", url)
        self.set_property(node_id, "inputs/save_to", save_to)
        self.set_property(node_id, "inputs/filename", filename)
        self.set_property(node_id, "inputs/token", token)

    def add_lora_node(
        self,
        sampler_node_id: str,
        prompt_node_id: str,
        negative_prompt_node_id: str,
        lora_name: str,
        strength_model: float = 1,
        strength_clip: float = 1,
    ):
        lora_id = str(max([int(node_id) for node_id in self._workflow_api]) + 1)
        self._workflow_api[lora_id] = deepcopy(LORA_NODE)
        model_src_id = self.get_property(sampler_node_id, "inputs/model")[0]
        clip_src_id = self.get_property(prompt_node_id, "inputs/clip")[0]
        self.set_property(lora_id, "inputs/lora_name", lora_name)
        self.set_property(lora_id, "inputs/strength_model", strength_model)
        self.set_property(lora_id, "inputs/strength_clip", strength_clip)
        self.set_property(lora_id, "inputs/model", [model_src_id, 0])
        self.set_property(lora_id, "inputs/clip", [clip_src_id, 1])

        self.set_property(sampler_node_id, "inputs/model", [lora_id, 0])
        self.set_property(prompt_node_id, "inputs/clip", [lora_id, 1])
        self.set_property(negative_prompt_node_id, "inputs/clip", [lora_id, 1])

    def add_flux_guidance(self, sampler_node_id: str | None, guidance: float):
        new_node_id = str(max([int(node_id) for node_id in self._workflow_api]) + 1)
        self._workflow_api[new_node_id] = deepcopy(FluxGuidanceNode)
        self.set_property(new_node_id, "inputs/guidance", guidance)
        self.set_property(
            new_node_id,
            "inputs/conditioning",
            [self.get_property(sampler_node_id, "inputs/positive")[0], 0],
        )
        self.set_property(sampler_node_id, "inputs/positive", [new_node_id, 0])
