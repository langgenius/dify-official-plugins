import json
from typing import Any, Generator, Mapping
from werkzeug import Request, Response
from dify_plugin import Endpoint
from endpoints.auth import BaseAuth

class OpenaiCompatible(Endpoint, BaseAuth):
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
        app_id: str = settings.get("app_id", {}).get("app_id", "")
        if not app_id:
            raise ValueError("App ID is required")
        if not isinstance(app_id, str):
            raise ValueError("App ID must be a string")

        memory_mode: str = settings.get("memory_mode", "last_user_message")
        try:
            data = r.get_json()
            messages = data.get("messages", [])
            stream = data.get("stream", False)

            conversation_id, query = self._get_memory(memory_mode, messages)

            if stream:

                def generator():
                    response = self.session.app.chat.invoke(
                        app_id=app_id,
                        inputs={
                            "messages": json.dumps(messages),
                        },
                        query=query,
                        response_mode="streaming",
                        conversation_id=conversation_id,
                    )

                    return self._handle_chat_stream_message(app_id, response)

                return Response(
                    generator(),
                    status=200,
                    content_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Transfer-Encoding": "chunked",
                    },
                )
            else:
                response = self.session.app.chat.invoke(
                    app_id=app_id,
                    inputs={
                        "messages": json.dumps(messages),
                    },
                    query=query,
                    response_mode="blocking",
                    conversation_id=conversation_id,
                )
                return Response(
                    self._handle_chat_blocking_message(app_id, response),
                    status=200,
                    content_type="text/html",
                )
        except ValueError as e:
            return Response(f"Error: {e}", status=400, content_type="text/plain")
        except Exception as e:
            return Response(f"Error: {e}", status=500, content_type="text/plain")

    def _get_memory(
        self, memory_mode: str, messages: list[dict[str, Any]]
    ) -> tuple[str, str]:
        """
        Get the memory from the messages

        returns:
            - conversation_id: str
            - query: str
        """
        if memory_mode == "last_user_message":
            user_message = ""
            for message in reversed(messages):
                if message.get("role") == "user":
                    user_message = message.get("content")
                    break

            if not user_message:
                raise ValueError("No user message found")

            return "", user_message
        else:
            raise ValueError(
                f"Invalid memory mode: {memory_mode}, only support last_user_message for now"
            )

    def _handle_chat_stream_message(
        self, app_id: str, generator: Generator[dict[str, Any], None, None]
    ) -> Generator[str, None, None]:
        """
        Handle the chat stream
        """
        message_id = ""
        for data in generator:
            if data.get("event") == "agent_message" or data.get("event") == "message":
                message = {
                    "id": "chatcmpl-" + data.get("message_id", "none"),
                    "object": "chat.completion.chunk",
                    "created": int(data.get("created", 0)),
                    "model": "gpt-3.5-turbo",
                    "system_fingerprint": "difyai",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": data.get("answer", ""),
                            },
                            "finish_reason": None,
                        }
                    ],
                }
                message_id = message.get("id", "none")
                yield f"data: {json.dumps(message)}\n\n"
            elif data.get("event") == "message_end":
                message = {
                    "id": "chatcmpl-" + data.get("message_id", "none"),
                    "object": "chat.completion.chunk",
                    "created": int(data.get("created", 0)),
                    "model": "gpt-3.5-turbo",
                    "system_fingerprint": "difyai",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "completion_tokens": data.get("metadata", {})
                        .get("usage", {})
                        .get("completion_tokens", 0),
                        "prompt_tokens": data.get("metadata", {})
                        .get("usage", {})
                        .get("prompt_tokens", 0),
                        "total_tokens": data.get("metadata", {})
                        .get("usage", {})
                        .get("total_tokens", 0),
                    },
                }
                yield f"data: {json.dumps(message)}\n\n"
            elif data.get("event") == "message_file":
                url = data.get("url", "")
                message = {
                    "id": "chatcmpl-" + message_id,
                    "object": "chat.completion.chunk",
                    "created": int(data.get("created", 0)),
                    "model": "gpt-3.5-turbo",
                    "system_fingerprint": "difyai",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": f"[{data.get('id', 'none')}]({url})",
                            },
                        }
                    ],
                }
                yield f"data: {json.dumps(message)}\n\n"

        yield "data: [DONE]\n\n"

    def _handle_chat_blocking_message(
        self, app_id: str, response: dict[str, Any]
    ) -> str:
        """
        Handle the chat blocking message
        """
        message = {
            "id": "chatcmpl-" + response.get("id", "none"),
            "object": "chat.completion",
            "created": int(response.get("created", 0)),
            "model": "gpt-3.5-turbo",
            "system_fingerprint": "difyai",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response.get("answer", ""),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "completion_tokens": response.get("metadata", {})
                .get("usage", {})
                .get("completion_tokens", 0),
                "prompt_tokens": response.get("metadata", {})
                .get("usage", {})
                .get("prompt_tokens", 0),
            },
        }

        return json.dumps(message)
