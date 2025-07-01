import json
import os
from copy import deepcopy
import random

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


class ComfyUiWorkflow:
    def __init__(self, workflow_json_str: str):
        self._workflow_json: dict = json.loads(workflow_json_str)

    def __str__(self):
        return str(self._workflow_json).replace("'", '"')

    def get_json(self) -> dict:
        return self._workflow_json

    def get_property(self, node_id: str, path: str):
        try:
            workflow_json = self._workflow_json[node_id]
            for name in path.split("/")[:-1]:
                workflow_json = workflow_json[name]
            return workflow_json[path.split("/")[-1]]
        except:
            return None

    def set_property(self, node_id: str, path: str, value, can_create=False):
        workflow_json = self._workflow_json[node_id]
        for name in path.split("/")[:-1]:
            if not can_create and name not in workflow_json:
                raise Exception(f"Cannot create a new property.")
            workflow_json = workflow_json[name]
        workflow_json[path.split("/")[-1]] = value

    def get_class_type(self, node_id):
        return self.get_property(node_id, "class_type")

    def get_node_ids_by_class_type(self, class_type: str) -> list[str]:
        node_ids = []
        for node_id in self._workflow_json:
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
        for node_id in self._workflow_json:
            if self.get_property(node_id, "inputs/seed") is not None:
                self.set_property(
                    node_id, "inputs/seed", random.randint(10**14, 10**15 - 1)
                )
            if self.get_property(node_id, "inputs/noise_seed") is not None:
                self.set_property(
                    node_id, "inputs/noise_seed", random.randint(10**14, 10**15 - 1)
                )

    def set_image_names(
        self, image_names: list[str], ordered_node_ids: list[str] = None
    ):
        if ordered_node_ids is None:
            ordered_node_ids = self.get_node_ids_by_class_type("LoadImage")
        for i, node_id in enumerate(ordered_node_ids):
            self.set_property(node_id, "inputs/image", image_names[i])

    def set_model_loader(self, node_id: str, ckpt_name: str):
        if node_id is None:
            node_id = self.identify_node_by_class_type("CheckpointLoaderSimple")
        if self.get_property(node_id, "class_type") != "CheckpointLoaderSimple":
            raise Exception(f"Node {node_id} is not CheckpointLoaderSimple")
        self.set_property(node_id, "inputs/ckpt_name", ckpt_name)

    def set_Ksampler(
        self,
        node_id: str,
        steps: int,
        sampler_name: str,
        scheduler_name: str,
        cfg: float,
        denoise: float,
        seed: int,
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
        self.set_property(node_id, "inputs/seed", seed)

    def set_empty_latent_image(
        self,
        node_id: str,
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

    def set_prompt(self, node_id: str, prompt: str):
        if node_id is None:
            node_id = self.identify_node_by_class_type("CLIPTextEncode")
        if self.get_class_type(node_id) != "CLIPTextEncode":
            raise Exception(f"Node {node_id} is not CLIPTextEncode")
        self.set_property(node_id, "inputs/text", prompt)

    def add_lora_node(
        self,
        sampler_node_id: str,
        prompt_node_id: str,
        negative_prompt_node_id: str,
        lora_name: str,
        strength_model: float = 1,
        strength_clip: float = 1,
    ):
        lora_id = str(max([int(node_id) for node_id in self._workflow_json]) + 1)
        self._workflow_json[lora_id] = deepcopy(LORA_NODE)
        model_src_id = self.get_property(sampler_node_id, "inputs/model")[0]
        clip_src_id = self.get_property(prompt_node_id, "inputs/clip")[0]
        self.set_property(lora_id, "inputs/lora_name", lora_name)
        self.set_property(lora_id, "inputs/strength_model", strength_model)
        self.set_property(lora_id, "inputs/strength_clip", strength_clip)
        self.set_property(lora_id, "inputs/model", [model_src_id, 0])
        self.set_property(lora_id, "inputs/clip", [clip_src_id, 1])

        self.set_property(sampler_node_id, "inputs/model", [lora_id, 0])
        self.set_property(prompt_node_id, "inputs/model", [lora_id, 0])
        self.set_property(prompt_node_id, "inputs/clip", [lora_id, 1])
        self.set_property(negative_prompt_node_id, "inputs/model", [lora_id, 0])
        self.set_property(negative_prompt_node_id, "inputs/clip", [lora_id, 1])

    def add_flux_guidance(self, sampler_node_id: str, guidance: float):
        new_node_id = str(max([int(node_id) for node_id in self._workflow_json]) + 1)
        self._workflow_json[new_node_id] = deepcopy(FluxGuidanceNode)
        self.set_property(new_node_id, "inputs/guidance", guidance)
        self.set_property(
            new_node_id,
            "inputs/conditioning",
            [self.get_property(sampler_node_id, "inputs/positive")[0], 0],
        )
        self.set_property(sampler_node_id, "inputs/positive", [new_node_id, 0])


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.realpath(__file__))
    workflow_path = os.path.join(current_dir, "json", "txt2img.json")
    wk = ComfyUiWorkflow(open(workflow_path, "r").read())
    for ksamplerId in wk.get_node_ids_by_class_type("KSampler"):
        wk.set_property(ksamplerId, "inputs/sampler_name", "sampleeer")
    wk.add_lora_node("3", "6", "7", "hello", 0.5)
    wk.add_lora_node("3", "6", "7", "world")
    wk.add_lora_node("3", "6", "7", "!!!", 0.2, 2)
    with open("a.json", "w") as f:
        f.write(str(wk))
