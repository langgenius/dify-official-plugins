import json
from typing import cast

from dify_plugin.entities.tool import ToolInvokeMessage


def append_tool_result(parts: list[str], content: str) -> None:
    if not content:
        return

    parts.append(content)


def render_tool_invoke_response(response: ToolInvokeMessage) -> str:
    if response.type == ToolInvokeMessage.MessageType.TEXT:
        return cast(ToolInvokeMessage.TextMessage, response.message).text

    if response.type == ToolInvokeMessage.MessageType.LINK:
        return (
            f"result link: {cast(ToolInvokeMessage.TextMessage, response.message).text}."
            + " please tell user to check it."
        )

    if response.type in {
        ToolInvokeMessage.MessageType.IMAGE_LINK,
        ToolInvokeMessage.MessageType.IMAGE,
    }:
        image_link_text = cast(ToolInvokeMessage.TextMessage, response.message).text
        return (
            f"Image has been successfully generated and saved to: {image_link_text}. "
            + "The image file is now available for download. "
            + "Please inform the user that the image has been created successfully."
        )

    if response.type == ToolInvokeMessage.MessageType.JSON:
        return json.dumps(
            cast(ToolInvokeMessage.JsonMessage, response.message).json_object,
            ensure_ascii=False,
        )

    if response.type == ToolInvokeMessage.MessageType.BLOB:
        return "Generated file ... "

    return str(response.message)
