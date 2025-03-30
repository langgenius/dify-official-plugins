import json
import time
from typing import Mapping, Optional
import uuid
from werkzeug import Request, Response
from dify_plugin import Endpoint
from dify_plugin.entities.model.llm import (
    LLMModelConfig,
)
from dify_plugin.entities.model.message import (
    PromptMessage,
    UserPromptMessage,
    AssistantPromptMessage,
    ToolPromptMessage,
    SystemPromptMessage,
    PromptMessageTool,
)

from endpoints.auth import BaseAuth


class OaicompatDifyModelEndpoint(Endpoint, BaseAuth):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        """
        Invokes the endpoint with the given request.
        """
        if not self.verify(r, settings):
            return Response(
                json.dumps({"message": "Unauthorized"}),
                status=401,
                content_type="application/json",
            )

        llm: Optional[dict] = settings.get("llm")
        if not llm:
            raise ValueError("LLM is not set")        

        if "completion_params" not in llm:
            llm["completion_params"] = {}

        data = r.get_json(force=True)
        if not data:
            raise ValueError("Request body is empty")

        prompt_messages: list[PromptMessage] = []
        if not isinstance(data.get("messages"), list) or not data.get("messages"):
            raise ValueError("Messages is not a list or empty")

        for message in data.get("messages", []):
            if message.get("role") == "user":
                prompt_messages.append(UserPromptMessage(content=message["content"]))
            elif message.get("role") == "assistant":
                prompt_messages.append(
                    AssistantPromptMessage(content=message["content"])
                )
            elif message.get("role") == "tool":
                prompt_messages.append(
                    ToolPromptMessage(
                        content=message["content"],
                        tool_call_id=message["tool_call_id"],
                    )
                )
            elif message.get("role") == "system":
                prompt_messages.append(SystemPromptMessage(content=message["content"]))
            else:
                raise ValueError(f"Invalid message role: {message.get('role')}")

        tools: list[PromptMessageTool] = []
        if data.get("tools"):
            for tool in data.get("tools", []):
                tools.append(PromptMessageTool(**tool))

        stream: bool = data.get("stream", False)

        def generator():
            if not stream:
                llm_invoke_response = self.session.model.llm.invoke(
                    model_config=LLMModelConfig(**llm),
                    prompt_messages=prompt_messages,
                    tools=tools,
                    stream=False,
                )

                yield json.dumps(
                    {
                        "id": "chatcmpl-" + str(uuid.uuid4()),
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": llm.get("model"),
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": llm_invoke_response.message.content,
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": llm_invoke_response.usage.prompt_tokens,
                            "completion_tokens": llm_invoke_response.usage.completion_tokens,
                            "total_tokens": llm_invoke_response.usage.total_tokens,
                        },
                    }
                )
            else:
                llm_invoke_response = self.session.model.llm.invoke(
                    model_config=LLMModelConfig(**llm),
                    prompt_messages=prompt_messages,
                    tools=tools,
                    stream=True,
                )

                for chunk in llm_invoke_response:
                    yield (
                        json.dumps(
                            {
                                "id": "chatcmpl-" + str(uuid.uuid4()),
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": llm.get("model"),
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {
                                            "content": chunk.delta.message.content
                                        },
                                        "finish_reason": None,
                                    }
                                ],
                            }
                        )
                        + "\n\n"
                    )

        return Response(
            generator(),
            status=200,
            content_type="event-stream" if stream else "application/json",
        )
