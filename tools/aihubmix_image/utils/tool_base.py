"""Shared behaviour for the two image tools.

Both tools do the same thing — resolve the model's schema, build a payload from whatever the
user filled in, run the task, hand back the bytes — and differ only in whether a source image
is required. Keeping the flow here means the model dropdown and the error messages stay
identical between them.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities import I18nObject, ParameterOption
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.protocol.dynamic_select import DynamicSelectProtocol

from utils import catalog, media, task
from utils.client import AIHubMixClient, GatewayError
from utils.schema import ImageEndpoint, build_payload, fetch_image_endpoint, parse_extra

# Everything the tool forms expose that maps onto a schema field of the same name.
SCALAR_PARAMETERS = (
    "n",
    "size",
    "aspect_ratio",
    "output_format",
    "seed",
    "negative_prompt",
)


class AIHubMixImageTool(Tool, DynamicSelectProtocol):
    #: Narrows the model dropdown to models that accept image input (the edit tool).
    requires_image_input = False

    def _client(self) -> AIHubMixClient:
        return AIHubMixClient(self.runtime.credentials or {})

    def fetch_parameter_options(self, parameter: str) -> list[ParameterOption]:
        if parameter != "model":
            return []
        models = catalog.list_image_models(self._client(), accepts_image=self.requires_image_input)
        return [
            ParameterOption(
                value=model.model_id,
                label=I18nObject(en_US=model.display_name, zh_Hans=model.display_name),
            )
            for model in models
        ]

    def _generate(
        self,
        tool_parameters: dict[str, Any],
        *,
        source_files: Any = None,
        mask: Any = None,
    ) -> Generator[ToolInvokeMessage, None, None]:
        client = self._client()
        endpoint = fetch_image_endpoint(client, str(tool_parameters.get("model") or ""))

        media_fields: dict[str, Any] = {}
        media_fields.update(media.source_images(endpoint, source_files, label="Input image"))
        mask_files = media.as_list(mask)
        if mask_files:
            media_fields["mask"] = media.to_reference(mask_files[0], label="Mask")

        payload, notes = build_payload(
            endpoint,
            prompt=str(tool_parameters.get("prompt") or ""),
            scalars={name: tool_parameters.get(name) for name in SCALAR_PARAMETERS},
            media=media_fields,
            extra=parse_extra(tool_parameters.get("extra")),
        )

        result = task.run(client, endpoint, payload)

        for index, image in enumerate(result.images, start=1):
            yield self.create_blob_message(
                blob=image.data,
                meta={
                    "mime_type": image.mime_type,
                    "filename": f"{result.model}-{result.task_id or index}-{index}.{image.extension}",
                },
            )

        yield self.create_json_message(
            {
                "task_id": result.task_id,
                "model": result.model,
                "status": result.status,
                "image_count": len(result.images),
                "request": _redacted(payload),
                "ignored_parameters": notes,
            }
        )

        if notes:
            yield self.create_text_message(
                "Some parameters were not sent because this model does not accept them:\n"
                + "\n".join(f"- {note}" for note in notes)
            )

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        raise NotImplementedError


def _redacted(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip inlined image bytes out of the echoed request — they are megabytes of base64."""
    summary: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str) and value.startswith("data:"):
            summary[key] = f"<inline {key}>"
        elif isinstance(value, list) and any(isinstance(item, str) and item.startswith("data:") for item in value):
            summary[key] = f"<{len(value)} inline {key}>"
        else:
            summary[key] = value
    return summary


__all__ = ["AIHubMixImageTool", "GatewayError", "ImageEndpoint"]
