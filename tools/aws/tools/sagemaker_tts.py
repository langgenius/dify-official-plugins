import json
from enum import Enum
from typing import Any, Optional, Union
from collections.abc import Generator

import boto3

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class TTSModelType(Enum):
    PresetVoice = "PresetVoice"
    CloneVoice = "CloneVoice"
    CloneVoice_CrossLingual = "CloneVoice_CrossLingual"
    InstructVoice = "InstructVoice"


class SageMakerTTSTool(Tool):
    sagemaker_endpoint: str | None = None

    def _detect_lang_code(
        self, content: str, comprehend_client: Any, map_dict: Optional[dict] = None
    ):
        map_dict = {
            "zh": "<|zh|>",
            "en": "<|en|>",
            "ja": "<|jp|>",
            "zh-TW": "<|yue|>",
            "ko": "<|ko|>",
        }

        response = comprehend_client.detect_dominant_language(Text=content)
        language_code = response["Languages"][0]["LanguageCode"]
        return map_dict.get(language_code, "<|zh|>")

    def _build_tts_payload(
        self,
        model_type: str,
        content_text: str,
        model_role: str,
        prompt_text: str,
        prompt_audio: str,
        instruct_text: str,
        comprehend_client: Any,
    ):
        if model_type == TTSModelType.PresetVoice.value and model_role:
            return {"tts_text": content_text, "role": model_role}
        if model_type == TTSModelType.CloneVoice.value and prompt_text and prompt_audio:
            return {
                "tts_text": content_text,
                "prompt_text": prompt_text,
                "prompt_audio": prompt_audio,
            }
        if model_type == TTSModelType.CloneVoice_CrossLingual.value and prompt_audio:
            lang_tag = self._detect_lang_code(content_text, comprehend_client)
            return {
                "tts_text": f"{content_text}",
                "prompt_audio": prompt_audio,
                "lang_tag": lang_tag,
            }
        if (
            model_type == TTSModelType.InstructVoice.value
            and instruct_text
            and model_role
        ):
            return {
                "tts_text": content_text,
                "role": model_role,
                "instruct_text": instruct_text,
            }

        raise RuntimeError(f"Invalid params for {model_type}")

    def _invoke_sagemaker(self, payload: dict, endpoint: str, sagemaker_client: Any):
        response_model = sagemaker_client.invoke_endpoint(
            EndpointName=endpoint,
            Body=json.dumps(payload),
            ContentType="application/json",
        )
        json_str = response_model["Body"].read().decode("utf8")
        json_obj = json.loads(json_str)
        return json_obj

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        """
        invoke tools
        """
        try:
            aws_region = tool_parameters.get("aws_region")

            # Build fresh clients per invocation so disk-refreshed
            # credentials are picked up on every call. See issue #3544.
            session = boto3.Session(region_name=aws_region)
            sagemaker_client = session.client("sagemaker-runtime")
            comprehend_client = session.client("comprehend")

            if not self.sagemaker_endpoint:
                self.sagemaker_endpoint = tool_parameters.get("sagemaker_endpoint")

            tts_text = tool_parameters.get("tts_text")
            tts_infer_type = tool_parameters.get("tts_infer_type")

            voice = tool_parameters.get("voice")
            mock_voice_audio = tool_parameters.get("mock_voice_audio")
            mock_voice_text = tool_parameters.get("mock_voice_text")
            voice_instruct_prompt = tool_parameters.get("voice_instruct_prompt")
            payload = self._build_tts_payload(
                tts_infer_type,
                tts_text,
                voice,
                mock_voice_text,
                mock_voice_audio,
                voice_instruct_prompt,
                comprehend_client=comprehend_client,
            )

            result = self._invoke_sagemaker(
                payload, self.sagemaker_endpoint, sagemaker_client
            )

            yield self.create_text_message(text=result["s3_presign_url"])

        except Exception as e:
            yield self.create_text_message(f"Exception {str(e)}")
