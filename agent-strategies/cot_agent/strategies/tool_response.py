from collections.abc import Mapping

from dify_plugin.entities.tool import ToolInvokeMessage


def should_forward_file_message(response: ToolInvokeMessage) -> bool:
    if response.type in {
        ToolInvokeMessage.MessageType.FILE,
        ToolInvokeMessage.MessageType.BLOB,
        ToolInvokeMessage.MessageType.IMAGE,
        ToolInvokeMessage.MessageType.IMAGE_LINK,
    }:
        return True
    if response.type != ToolInvokeMessage.MessageType.LINK:
        return False

    meta = response.meta
    if not isinstance(meta, Mapping):
        return False
    tool_file_id = meta.get("tool_file_id")
    return (isinstance(tool_file_id, str) and bool(tool_file_id)) or "file" in meta
