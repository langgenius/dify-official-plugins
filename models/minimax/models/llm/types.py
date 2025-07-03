from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class MinimaxMessage(BaseModel):
    class Role(Enum):
        USER = "USER"
        ASSISTANT = "BOT"
        SYSTEM = "SYSTEM"
        FUNCTION = "FUNCTION"

    role: str = Role.USER.value
    content: str
    usage: Optional[dict[str, int]] = None
    stop_reason: str = ""
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_call_id: Optional[str] = Field(
        default=None,
        description="ID that must be included in tool messages, exactly matching the ID returned by the API"
    )
    function_call: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:

        """
        Convert to V2 API format (OpenAI compatible format)
        """
        if self.role == MinimaxMessage.Role.ASSISTANT.value and self.tool_calls:
            return {
                "role": "assistant",
                "content": self.content,
                "tool_calls": self.tool_calls
            }
        elif self.role == MinimaxMessage.Role.FUNCTION.value and self.tool_call_id:
            return {
                "role": "tool",
                "content": self.content,
                "tool_call_id": self.tool_call_id
            }
        else:
            return {
                "role": self.role.lower() if self.role in ["USER", "SYSTEM"] else "assistant",
                "content": self.content
            }

    def to_completion_dict(self) -> dict[str, Any]:
        """
        Convert to original API format (used by chat_completion.py)
        """
        return {
            "sender_type": self.role,
            "text": self.content
        }

    def to_pro_dict(self) -> dict[str, Any]:
        """
        Convert to Pro API format (used by chat_completion_pro.py)
        """
        # Role name mapping
        role_name_mapping = {
            "USER": "User",
            "BOT": "Expert",
            "SYSTEM": "System",
            "FUNCTION": "Tool"
        }

        result = {
            "sender_type": self.role,
            "sender_name": role_name_mapping.get(self.role, "User"),
            "text": self.content
        }

        # If it's an assistant message with a function call, add function call information
        if self.role == MinimaxMessage.Role.ASSISTANT.value and self.function_call:
            result["function_call"] = self.function_call

        return result

    def __init__(self, content: str, role: str = "USER", **kwargs) -> None:
        super().__init__(**{"content": content, "role": role, **kwargs})
        # Only set to None if not already provided
        if not hasattr(self, 'tool_call_id') or self.tool_call_id is None:
            self.tool_call_id = None
        if not hasattr(self, 'tool_calls') or self.tool_calls is None:
            self.tool_calls = None
