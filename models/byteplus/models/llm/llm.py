import json
import logging
from collections.abc import Generator
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, TypeVar, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime._streaming import Stream
from volcenginesdkarkruntime.types.chat import ChatCompletion, ChatCompletionChunk

from dify_plugin.entities.model.llm import (
    LLMPollingResult,
    LLMPollingStatus,
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    AudioPromptMessageContent,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
    VideoPromptMessageContent,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlatformSpec:
    name: str
    seedance_prefix: str
    seedream_prefix: str
    supports_web_search: bool


BYTEPLUS_PLATFORM = PlatformSpec(
    name="byteplus",
    seedance_prefix="seedance-",
    seedream_prefix="seedream-",
    supports_web_search=False,
)
PLATFORM_SPECS = (BYTEPLUS_PLATFORM,)

SEEDANCE_RUNNING_STATUSES = {"queued", "running"}
SEEDANCE_FAILED_STATUSES = {"failed", "expired", "cancelled"}
DEFAULT_POLLING_INTERVAL_SECONDS = 10
DEFAULT_POLLING_EXPIRES_AFTER_SECONDS = 1800
DEFAULT_POLLING_MAX_ATTEMPTS = 60
DEFAULT_SEEDANCE_INPUT_MODE = "first_frame"
SEEDANCE_INPUT_MODES = {"first_frame", "first_last_frame", "reference_image"}
SEEDANCE_IMAGE_ROLES = {"first_frame", "last_frame", "reference_image"}

SEEDANCE_MODEL_PARAMETER_NAMES = {
    "ratio",
    "duration",
    "frames",
    "resolution",
    "seed",
    "camera_fixed",
    "generate_audio",
    "watermark",
    "return_last_frame",
    "draft",
    "callback_url",
    "safety_identifier",
    "service_tier",
    "execution_expires_after",
    "priority",
}
SEEDREAM_MODEL_PARAMETER_NAMES = {
    "size",
    "response_format",
    "watermark",
    "sequential_image_generation",
    "sequential_image_generation_options",
    "guidance_scale",
    "output_format",
    "optimize_prompt_options",
}

JSON_OBJECT_ADAPTER = TypeAdapter(dict[str, Any])
ModelT = TypeVar("ModelT", bound=BaseModel)


class ArkHTTPError(Exception):
    def __init__(self, status_code: int, response_text: str) -> None:
        super().__init__(
            f"API request failed with status code {status_code}: {response_text}"
        )
        self.status_code = status_code
        self.response_text = response_text


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class ProviderModel(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class ArkObjectResponse(ProviderModel):
    pass


class ArkCredentials(RequestModel):
    ark_api_key: str = Field(min_length=1)
    api_endpoint_host: str = Field(min_length=1)


class ArkURL(RequestModel):
    url: str = Field(min_length=1)


class ChatContentImageURL(RequestModel):
    url: str = Field(min_length=1)
    detail: Literal["high", "low"] | None = None


class ChatContentVideoURL(RequestModel):
    url: str = Field(min_length=1)


class ChatTextContent(RequestModel):
    type: Literal["text"] = "text"
    text: str


class ChatImageContent(RequestModel):
    type: Literal["image_url"] = "image_url"
    image_url: ChatContentImageURL


class ChatVideoContent(RequestModel):
    type: Literal["video_url"] = "video_url"
    video_url: ChatContentVideoURL


ChatContentPart = ChatTextContent | ChatImageContent | ChatVideoContent


class ChatToolCallFunction(RequestModel):
    name: str
    arguments: str


class ChatToolCall(RequestModel):
    id: str
    type: str = "function"
    function: ChatToolCallFunction


class ChatMessage(RequestModel):
    role: str = Field(min_length=1)
    content: str | list[ChatContentPart]
    tool_call_id: str | None = None
    tool_calls: list[ChatToolCall] | None = None


class ChatFunction(RequestModel):
    name: str = Field(min_length=1)
    description: str | None = None
    parameters: dict[str, Any] | None = None


class ChatTool(RequestModel):
    type: Literal["function"] = "function"
    function: ChatFunction


class ChatThinking(RequestModel):
    type: str = Field(min_length=1)


class ChatStreamOptions(RequestModel):
    include_usage: bool | None = None


class ChatToolChoiceFunction(RequestModel):
    name: str = Field(min_length=1)


class ChatToolChoiceObject(RequestModel):
    type: Literal["function"] = "function"
    function: ChatToolChoiceFunction


ChatToolChoice = Literal["none", "auto", "required"] | ChatToolChoiceObject


class ChatCompletionRequest(RequestModel):
    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: list[str] | None = None
    user: str | None = None
    thinking: ChatThinking | None = None
    reasoning_effort: Literal["minimal"] | None = None
    tools: list[ChatTool] | None = None
    tool_choice: ChatToolChoice | None = None
    parallel_tool_calls: bool | None = None
    stream_options: ChatStreamOptions | None = None


class SeedanceTextContent(RequestModel):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1)


class SeedanceImageContent(RequestModel):
    type: Literal["image_url"] = "image_url"
    image_url: ArkURL
    role: str = Field(min_length=1)


class SeedanceVideoContent(RequestModel):
    type: Literal["video_url"] = "video_url"
    video_url: ArkURL
    role: str = Field(min_length=1)


class SeedanceAudioContent(RequestModel):
    type: Literal["audio_url"] = "audio_url"
    audio_url: ArkURL
    role: str = Field(min_length=1)


SeedanceContentPart = (
    SeedanceTextContent
    | SeedanceImageContent
    | SeedanceVideoContent
    | SeedanceAudioContent
)


class WebSearchTool(RequestModel):
    type: Literal["web_search"] = "web_search"


class SequentialImageGenerationOptions(RequestModel):
    max_images: int = Field(ge=1)


class SeedanceGenerationRequest(RequestModel):
    model: str = Field(min_length=1)
    content: list[SeedanceContentPart] = Field(min_length=1)
    ratio: str | None = None
    duration: int | None = None
    frames: int | None = None
    resolution: str | None = None
    seed: int | None = None
    camera_fixed: bool | None = None
    generate_audio: bool | None = None
    watermark: bool | None = None
    return_last_frame: bool | None = None
    draft: bool | None = None
    callback_url: str | None = None
    safety_identifier: str | None = None
    service_tier: str | None = None
    execution_expires_after: int | None = None
    priority: int | None = None
    tools: list[WebSearchTool] | None = None


class SeedreamGenerationRequest(RequestModel):
    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    size: str | None = None
    response_format: str | None = None
    watermark: bool | None = None
    sequential_image_generation: str | None = None
    sequential_image_generation_options: SequentialImageGenerationOptions | None = None
    guidance_scale: float | None = None
    output_format: str | None = None
    optimize_prompt_options: dict[str, Any] | None = None
    image: str | list[str] | None = None
    tools: list[WebSearchTool] | None = None


class ProviderError(ProviderModel):
    code: str | None = None
    message: str | None = None

    def format(self) -> str:
        if self.code and self.message:
            return f"{self.code}: {self.message}"
        if self.message:
            return self.message
        if self.code:
            return self.code
        return "provider request failed"


class ProviderUsage(ProviderModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class SeedanceTaskContent(ProviderModel):
    video_url: str | None = None
    last_frame_url: str | None = None


class SeedanceTaskResponse(ProviderModel):
    id: str = Field(min_length=1)
    status: str = Field(default="running", min_length=1)
    content: SeedanceTaskContent | None = None
    error: ProviderError | str | None = None
    usage: ProviderUsage | None = None


class SeedreamImageResponse(ProviderModel):
    url: str | None = None
    b64_json: str | None = None
    error: ProviderError | str | None = None


class SeedreamGenerationResponse(ProviderModel):
    error: ProviderError | str | None = None
    data: list[SeedreamImageResponse] | None = None
    usage: ProviderUsage | None = None


class SeedancePollingState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    task_id: str = Field(min_length=1)
    model: str | None = None
    platform: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def build_model(model_cls: type[ModelT], context: str, **data: Any) -> ModelT:
    try:
        return model_cls(**data)
    except ValidationError as error:
        raise InvokeError(f"{context}: {error}") from error


def parse_model(
    model_cls: type[ModelT], payload: Mapping[str, Any], context: str
) -> ModelT:
    try:
        return model_cls.model_validate(payload)
    except ValidationError as error:
        raise InvokeError(f"{context}: {error}") from error


def failed_polling_result_from_validation(error: InvokeError) -> LLMPollingResult:
    return LLMPollingResult(status=LLMPollingStatus.FAILED, error=str(error))


def convert_prompt_message_tool(tool: PromptMessageTool) -> ChatTool:
    return build_model(
        ChatTool,
        "Invalid chat tool",
        function=build_model(
            ChatFunction,
            "Invalid chat tool function",
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
        ),
    )


def convert_content_to_chat_content(content: Any) -> str | list[ChatContentPart] | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    parts: list[ChatContentPart] = []
    for message_content in content:
        if message_content.type == PromptMessageContentType.TEXT:
            message_content = cast(TextPromptMessageContent, message_content)
            parts.append(
                build_model(
                    ChatTextContent,
                    "Invalid chat text content",
                    text=message_content.data,
                )
            )
        elif message_content.type == PromptMessageContentType.IMAGE:
            message_content = cast(ImagePromptMessageContent, message_content)
            detail = (
                "high"
                if message_content.detail == ImagePromptMessageContent.DETAIL.HIGH
                else "low"
            )
            parts.append(
                build_model(
                    ChatImageContent,
                    "Invalid chat image content",
                    image_url=build_model(
                        ChatContentImageURL,
                        "Invalid chat image URL",
                        url=message_content.data,
                        detail=detail,
                    ),
                )
            )
        elif message_content.type == PromptMessageContentType.VIDEO:
            message_content = cast(VideoPromptMessageContent, message_content)
            parts.append(
                build_model(
                    ChatVideoContent,
                    "Invalid chat video content",
                    video_url=build_model(
                        ChatContentVideoURL,
                        "Invalid chat video URL",
                        url=message_content.data,
                    ),
                )
            )
        elif message_content.type == PromptMessageContentType.AUDIO:
            message_content = cast(AudioPromptMessageContent, message_content)
            parts.append(
                build_model(
                    ChatTextContent,
                    "Invalid chat audio content",
                    text=message_content.data,
                )
            )
        elif message_content.type == PromptMessageContentType.DOCUMENT:
            message_content = cast(DocumentPromptMessageContent, message_content)
            parts.append(
                build_model(
                    ChatTextContent,
                    "Invalid chat document content",
                    text=message_content.data,
                )
            )
        else:
            parts.append(
                build_model(
                    ChatTextContent,
                    "Invalid chat fallback content",
                    text=str(message_content),
                )
            )

    return parts


def convert_prompt_message(message: PromptMessage) -> ChatMessage:
    if isinstance(message, SystemPromptMessage):
        return build_model(
            ChatMessage,
            "Invalid system chat message",
            role="system",
            content=convert_content_to_chat_content(message.content) or "",
        )

    if isinstance(message, UserPromptMessage):
        return build_model(
            ChatMessage,
            "Invalid user chat message",
            role="user",
            content=convert_content_to_chat_content(message.content) or "",
        )

    if isinstance(message, AssistantPromptMessage):
        tool_calls: list[ChatToolCall] | None = None
        if message.tool_calls:
            tool_calls = [
                build_model(
                    ChatToolCall,
                    "Invalid assistant tool call",
                    id=call.id,
                    type=call.type or "function",
                    function=build_model(
                        ChatToolCallFunction,
                        "Invalid assistant tool call function",
                        name=call.function.name,
                        arguments=call.function.arguments,
                    ),
                )
                for call in message.tool_calls
            ]

        return build_model(
            ChatMessage,
            "Invalid assistant chat message",
            role="assistant",
            content=convert_content_to_chat_content(message.content) or "",
            tool_calls=tool_calls,
        )

    if isinstance(message, ToolPromptMessage):
        return build_model(
            ChatMessage,
            "Invalid tool chat message",
            role="tool",
            content=convert_content_to_chat_content(message.content) or "",
            tool_call_id=message.tool_call_id,
        )

    role = getattr(getattr(message, "role", None), "value", None) or "user"
    return build_model(
        ChatMessage,
        "Invalid fallback chat message",
        role=role,
        content=convert_content_to_chat_content(getattr(message, "content", "")) or "",
    )


def wrap_thinking(
    content: str, reasoning_content: str | None, is_reasoning: bool
) -> tuple[str, bool]:
    content = content or ""

    if reasoning_content:
        if not is_reasoning:
            return "<think>\n" + reasoning_content, True
        return reasoning_content, True

    if is_reasoning:
        return "\n</think>" + (content or ""), False

    return content, False


def platform_spec_for_model(model: str) -> PlatformSpec | None:
    for platform in PLATFORM_SPECS:
        if model.startswith(platform.seedance_prefix) or model.startswith(
            platform.seedream_prefix
        ):
            return platform
    return None


def platform_name_for_model(model: str) -> str:
    platform = platform_spec_for_model(model)
    return platform.name if platform else "unknown"


def is_seedance_2_model(model: str) -> bool:
    platform = platform_spec_for_model(model)
    return bool(platform and model.startswith(f"{platform.seedance_prefix}2-"))


def is_seedance_model(model: str) -> bool:
    platform = platform_spec_for_model(model)
    return bool(platform and model.startswith(platform.seedance_prefix))


def is_seedream_model(model: str) -> bool:
    platform = platform_spec_for_model(model)
    return bool(platform and model.startswith(platform.seedream_prefix))


def filter_model_parameters(
    model_parameters: dict[str, Any],
    allowed_parameter_names: set[str],
) -> dict[str, Any]:
    return {
        key: value
        for key, value in model_parameters.items()
        if key in allowed_parameter_names and value is not None
    }


def extract_prompt_text(prompt_messages: list[PromptMessage]) -> str:
    text_parts: list[str] = []
    for message in prompt_messages:
        text = message.get_text_content().strip()
        if text:
            text_parts.append(text)
    return "\n".join(text_parts)


def iter_message_contents(prompt_messages: list[PromptMessage]):
    for message in prompt_messages:
        if not isinstance(message.content, list):
            continue
        yield from message.content


def content_role(content: object) -> str | None:
    opaque_body = getattr(content, "opaque_body", None)
    if isinstance(opaque_body, dict):
        role = opaque_body.get("role")
        if isinstance(role, str) and role:
            return role
    return None


def normalize_seedance_input_mode(value: object) -> str:
    if value is None or value == "":
        return DEFAULT_SEEDANCE_INPUT_MODE
    if not isinstance(value, str):
        raise InvokeError("Seedance input_mode must be a string.")
    input_mode = value.strip()
    if input_mode not in SEEDANCE_INPUT_MODES:
        raise InvokeError(
            "Seedance input_mode must be one of: first_frame, first_last_frame, reference_image."
        )
    return input_mode


def guess_format_from_url(url: str, default: str) -> str:
    suffix = PurePosixPath(url.split("?", 1)[0]).suffix.removeprefix(".").lower()
    return suffix or default


def guess_image_mime_type(*, url: str = "", output_format: str | None = None) -> str:
    image_format = (output_format or guess_format_from_url(url, "jpeg")).lower()
    if image_format == "jpg":
        image_format = "jpeg"
    return f"image/{image_format}"


def format_provider_error(error: object) -> str:
    if isinstance(error, ArkHTTPError):
        return str(error)
    if isinstance(error, ProviderError):
        return error.format()
    return str(error or "provider request failed")


def is_retryable_http_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def chat_stream_options_from_parameters(
    model_parameters: Mapping[str, Any],
) -> ChatStreamOptions:
    stream_options = model_parameters.get("stream_options")
    if stream_options is None:
        return ChatStreamOptions(include_usage=True)
    if isinstance(stream_options, ChatStreamOptions):
        return stream_options
    if not isinstance(stream_options, Mapping):
        raise InvokeError("Invalid chat stream options: expected an object.")
    return parse_model(ChatStreamOptions, stream_options, "Invalid chat stream options")


def build_chat_completion_request(
    *,
    model: str,
    prompt_messages: list[PromptMessage],
    model_parameters: Mapping[str, Any],
    tools: list[PromptMessageTool] | None,
    stop: list[str] | None,
    user: str | None,
    stream_options: ChatStreamOptions | None = None,
) -> ChatCompletionRequest:
    thinking: ChatThinking | None = None
    reasoning_effort: Literal["minimal"] | None = None
    thinking_type = model_parameters.get("thinking")
    if thinking_type:
        thinking = build_model(
            ChatThinking,
            "Invalid chat thinking options",
            type=thinking_type,
        )
        if thinking_type == "disabled":
            reasoning_effort = "minimal"

    return build_model(
        ChatCompletionRequest,
        "Invalid chat completion request",
        model=model,
        messages=[convert_prompt_message(message) for message in prompt_messages],
        temperature=model_parameters.get("temperature"),
        top_p=model_parameters.get("top_p"),
        max_tokens=model_parameters.get("max_tokens"),
        stop=stop,
        user=user,
        thinking=thinking,
        reasoning_effort=reasoning_effort,
        tools=[convert_prompt_message_tool(tool) for tool in tools] if tools else None,
        tool_choice=model_parameters.get("tool_choice")
        if "tool_choice" in model_parameters
        else None,
        parallel_tool_calls=model_parameters.get("parallel_tool_calls")
        if "parallel_tool_calls" in model_parameters
        else None,
        stream_options=stream_options,
    )


class BytePlusArkLargeLanguageModel(LargeLanguageModel):
    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {}

    def validate_credentials(self, model: str, credentials: Mapping[str, Any]) -> None:
        ark_credentials = parse_model(
            ArkCredentials,
            credentials,
            "Invalid Ark credentials",
        )
        if is_seedance_model(model) or is_seedream_model(model):
            self.validate_polling_credentials(model, ark_credentials)
            return

        try:
            client = Ark(
                base_url=ark_credentials.api_endpoint_host,
                api_key=ark_credentials.ark_api_key,
            )
            # minimal non-stream call
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=8,
            )
        except Exception as e:
            raise CredentialsValidateFailedError(e)

    def validate_polling_credentials(
        self, model: str, credentials: ArkCredentials
    ) -> None:
        path = (
            "contents/generations/tasks?page_num=1&page_size=1"
            if is_seedance_model(model)
            else "images/generations"
        )
        try:
            self.request_model(
                credentials=credentials,
                method="GET",
                path=path,
                response_model=ArkObjectResponse,
                response_context="Invalid Ark credential probe response",
            )
        except ArkHTTPError as error:
            if error.status_code in {400, 405}:
                return
            raise CredentialsValidateFailedError(error) from error
        except Exception as error:
            raise CredentialsValidateFailedError(error) from error

    def get_num_tokens(
        self,
        model: str,
        credentials: dict[str, Any],
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        # No official token counter exposed here; fall back to rough estimate.
        # This is acceptable for plugin implementations that do not support token counting.
        text = extract_prompt_text(prompt_messages)
        return max(1, len(text) // 4)

    def request_model(
        self,
        *,
        credentials: ArkCredentials,
        method: str,
        path: str,
        response_model: type[ModelT],
        response_context: str,
        payload: RequestModel | None = None,
    ) -> ModelT:
        endpoint_url = credentials.api_endpoint_host.rstrip("/") + "/"
        request_url = urljoin(endpoint_url, path.lstrip("/"))
        headers = {
            "Content-Type": "application/json",
            "Accept-Charset": "utf-8",
        }
        headers["Authorization"] = f"Bearer {credentials.ark_api_key}"

        data = (
            json.dumps(payload.to_payload()).encode("utf-8")
            if payload is not None
            else None
        )
        request = Request(request_url, data=data, headers=headers, method=method)

        try:
            with urlopen(request, timeout=60) as response:
                response_text = response.read().decode("utf-8", errors="replace")
        except HTTPError as error:
            response_text = error.read().decode("utf-8", errors="replace")
            raise ArkHTTPError(error.code, response_text) from error

        try:
            result = JSON_OBJECT_ADAPTER.validate_json(response_text)
        except ValidationError as error:
            raise InvokeError(f"API returned invalid JSON: {response_text}") from error
        return parse_model(response_model, result, response_context)

    def build_seedance_content(
        self,
        prompt_messages: list[PromptMessage],
        *,
        model: str,
        input_mode: object = None,
    ) -> list[SeedanceContentPart]:
        content: list[SeedanceContentPart] = []
        prompt_text = extract_prompt_text(prompt_messages)
        if prompt_text:
            content.append(
                build_model(
                    SeedanceTextContent,
                    "Invalid Seedance text content",
                    text=prompt_text,
                )
            )

        image_contents: list[ImagePromptMessageContent] = []
        video_contents: list[VideoPromptMessageContent] = []
        audio_contents: list[AudioPromptMessageContent] = []
        for message_content in iter_message_contents(prompt_messages):
            if isinstance(message_content, ImagePromptMessageContent):
                image_contents.append(message_content)
            elif isinstance(message_content, VideoPromptMessageContent):
                video_contents.append(message_content)
            elif isinstance(message_content, AudioPromptMessageContent):
                audio_contents.append(message_content)

        if (video_contents or audio_contents) and not is_seedance_2_model(model):
            raise InvokeError(
                "Seedance video and audio input is only supported by Seedance 2.0 models."
            )
        if len(video_contents) > 3:
            raise InvokeError("Seedance supports at most three reference videos.")
        if len(audio_contents) > 3:
            raise InvokeError("Seedance supports at most three reference audios.")
        if audio_contents and not (image_contents or video_contents):
            raise InvokeError(
                "Seedance audio input requires at least one reference image or video."
            )

        image_roles = self.build_seedance_image_roles(
            model=model,
            image_contents=image_contents,
            input_mode=input_mode,
            reference_mode=bool(video_contents or audio_contents),
        )
        for image_content, role in zip(image_contents, image_roles, strict=True):
            content.append(
                build_model(
                    SeedanceImageContent,
                    "Invalid Seedance image content",
                    image_url=build_model(
                        ArkURL,
                        "Invalid Seedance image URL",
                        url=image_content.data,
                    ),
                    role=role,
                )
            )

        for video_content in video_contents:
            content.append(
                build_model(
                    SeedanceVideoContent,
                    "Invalid Seedance video content",
                    video_url=build_model(
                        ArkURL,
                        "Invalid Seedance video URL",
                        url=video_content.data,
                    ),
                    role=content_role(video_content) or "reference_video",
                )
            )

        for audio_content in audio_contents:
            content.append(
                build_model(
                    SeedanceAudioContent,
                    "Invalid Seedance audio content",
                    audio_url=build_model(
                        ArkURL,
                        "Invalid Seedance audio URL",
                        url=audio_content.data,
                    ),
                    role=content_role(audio_content) or "reference_audio",
                )
            )

        if not content:
            raise InvokeError("Seedance requires prompt text or multimodal input.")
        return content

    def build_seedance_image_roles(
        self,
        *,
        model: str,
        image_contents: list[ImagePromptMessageContent],
        input_mode: object,
        reference_mode: bool,
    ) -> list[str]:
        if not image_contents:
            return []

        explicit_roles = [
            content_role(image_content) for image_content in image_contents
        ]
        if any(role is not None for role in explicit_roles):
            if any(role is None for role in explicit_roles):
                raise InvokeError(
                    "Seedance image roles must be provided for every image or omitted entirely."
                )
            roles = [cast(str, role) for role in explicit_roles]
            if reference_mode and any(role != "reference_image" for role in roles):
                raise InvokeError(
                    "Seedance video and audio input cannot be mixed with frame image roles."
                )
            self.validate_seedance_image_roles(model=model, roles=roles)
            return roles

        if reference_mode:
            if len(image_contents) > 9:
                raise InvokeError(
                    "Seedance reference_image input_mode supports at most nine images."
                )
            return ["reference_image" for _ in image_contents]

        normalized_input_mode = normalize_seedance_input_mode(input_mode)
        if normalized_input_mode == "first_frame":
            if len(image_contents) != 1:
                raise InvokeError(
                    "Seedance first_frame input_mode requires exactly one image."
                )
            return ["first_frame"]
        if normalized_input_mode == "first_last_frame":
            if len(image_contents) != 2:
                raise InvokeError(
                    "Seedance first_last_frame input_mode requires exactly two images."
                )
            return ["first_frame", "last_frame"]

        if not is_seedance_2_model(model):
            raise InvokeError(
                "Seedance reference_image input_mode is only supported by Seedance 2.0 models."
            )
        if len(image_contents) > 9:
            raise InvokeError(
                "Seedance reference_image input_mode supports at most nine images."
            )
        return ["reference_image" for _ in image_contents]

    def validate_seedance_image_roles(self, *, model: str, roles: list[str]) -> None:
        unsupported_roles = [role for role in roles if role not in SEEDANCE_IMAGE_ROLES]
        if unsupported_roles:
            raise InvokeError(
                f"Unsupported Seedance image role: {unsupported_roles[0]}"
            )
        if "reference_image" in roles:
            if any(role != "reference_image" for role in roles):
                raise InvokeError(
                    "Seedance reference_image cannot be mixed with frame roles."
                )
            if not is_seedance_2_model(model):
                raise InvokeError(
                    "Seedance reference_image role is only supported by Seedance 2.0 models."
                )
            if len(roles) > 9:
                raise InvokeError(
                    "Seedance reference_image role supports at most nine images."
                )
            return
        if roles == ["first_frame"]:
            return
        if roles == ["first_frame", "last_frame"]:
            return
        raise InvokeError(
            "Seedance frame roles must be first_frame or first_frame followed by last_frame."
        )

    def extract_seedream_images(
        self,
        prompt_messages: list[PromptMessage],
    ) -> list[str]:
        return [
            message_content.data
            for message_content in iter_message_contents(prompt_messages)
            if isinstance(message_content, ImagePromptMessageContent)
        ]

    def usage_from_provider_payload(
        self,
        *,
        model: str,
        credentials: ArkCredentials,
        usage_payload: ProviderUsage | None,
        completion_token_keys: tuple[str, ...],
    ):
        usage = usage_payload or ProviderUsage()
        prompt_tokens = usage.prompt_tokens or 0
        completion_tokens = 0
        for key in completion_token_keys:
            value = getattr(usage, key, None)
            if value is not None:
                completion_tokens = value
                break
        if completion_tokens == 0:
            completion_tokens = usage.total_tokens or 0
        return self._calc_response_usage(
            model=model,
            credentials=credentials.to_payload(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def seedance_polling_result_from_task(
        self,
        *,
        model: str,
        credentials: ArkCredentials,
        prompt_messages: list[PromptMessage],
        task_payload: SeedanceTaskResponse,
    ) -> LLMPollingResult:
        task_id = task_payload.id
        status = task_payload.status.lower()
        plugin_state = SeedancePollingState(
            task_id=task_id,
            model=model,
            platform=platform_name_for_model(model),
        ).to_payload()
        if status in SEEDANCE_RUNNING_STATUSES:
            return LLMPollingResult(
                status=LLMPollingStatus.RUNNING,
                plugin_state=plugin_state,
                next_check_after_seconds=DEFAULT_POLLING_INTERVAL_SECONDS,
                expires_after_seconds=DEFAULT_POLLING_EXPIRES_AFTER_SECONDS,
                max_attempts=DEFAULT_POLLING_MAX_ATTEMPTS,
            )

        if status in SEEDANCE_FAILED_STATUSES:
            return LLMPollingResult(
                status=LLMPollingStatus.FAILED,
                plugin_state=plugin_state,
                error=format_provider_error(task_payload.error),
            )

        if status != "succeeded":
            return LLMPollingResult(
                status=LLMPollingStatus.FAILED,
                plugin_state=plugin_state,
                error=f"Seedance returned unknown task status: {status}",
            )

        output_content = task_payload.content
        if output_content is None:
            return LLMPollingResult(
                status=LLMPollingStatus.FAILED,
                plugin_state=plugin_state,
                error="Seedance task succeeded without output content.",
            )
        video_url = output_content.video_url
        if not isinstance(video_url, str) or not video_url:
            return LLMPollingResult(
                status=LLMPollingStatus.FAILED,
                plugin_state=plugin_state,
                error="Seedance task succeeded without video_url.",
            )

        assistant_contents: list[Any] = [
            VideoPromptMessageContent(
                format=guess_format_from_url(video_url, "mp4"),
                mime_type="video/mp4",
                url=video_url,
                filename=f"{task_id}.mp4",
            )
        ]
        last_frame_url = output_content.last_frame_url
        if isinstance(last_frame_url, str) and last_frame_url:
            assistant_contents.append(
                ImagePromptMessageContent(
                    format=guess_format_from_url(last_frame_url, "jpeg"),
                    mime_type=guess_image_mime_type(url=last_frame_url),
                    url=last_frame_url,
                    filename=f"{task_id}-last-frame.jpg",
                )
            )

        return LLMPollingResult(
            status=LLMPollingStatus.SUCCEEDED,
            plugin_state=plugin_state,
            result=LLMResult(
                model=model,
                prompt_messages=prompt_messages,
                message=AssistantPromptMessage(content=assistant_contents),
                usage=self.usage_from_provider_payload(
                    model=model,
                    credentials=credentials,
                    usage_payload=task_payload.usage,
                    completion_token_keys=("completion_tokens",),
                ),
            ),
        )

    def _start_polling(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = False,
        user: str | None = None,
        *,
        workflow_run_id: str,
        node_id: str,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMPollingResult:
        del tools, stop, stream, workflow_run_id, node_id, json_schema
        ark_credentials = parse_model(
            ArkCredentials,
            credentials,
            "Invalid Ark credentials",
        )
        platform = platform_spec_for_model(model)
        if is_seedance_model(model):
            seedance_parameters = filter_model_parameters(
                model_parameters,
                SEEDANCE_MODEL_PARAMETER_NAMES,
            )
            if (
                platform
                and platform.supports_web_search
                and model_parameters.get("web_search")
            ):
                seedance_parameters["tools"] = [WebSearchTool()]
            if user:
                seedance_parameters["safety_identifier"] = user
            request_payload = build_model(
                SeedanceGenerationRequest,
                "Invalid Seedance generation request",
                model=model,
                content=self.build_seedance_content(
                    prompt_messages,
                    model=model,
                    input_mode=model_parameters.get("input_mode"),
                ),
                **seedance_parameters,
            )
            try:
                task_response = self.request_model(
                    credentials=ark_credentials,
                    method="POST",
                    path="contents/generations/tasks",
                    payload=request_payload,
                    response_model=SeedanceTaskResponse,
                    response_context="Invalid Seedance task response",
                )
            except ArkHTTPError as error:
                return LLMPollingResult(
                    status=LLMPollingStatus.FAILED,
                    error=format_provider_error(error),
                )
            except InvokeError as error:
                return failed_polling_result_from_validation(error)
            return self.seedance_polling_result_from_task(
                model=model,
                credentials=ark_credentials,
                prompt_messages=prompt_messages,
                task_payload=task_response,
            )

        if is_seedream_model(model):
            prompt = extract_prompt_text(prompt_messages)
            if not prompt:
                raise InvokeError("Seedream requires prompt text.")
            seedream_parameters = filter_model_parameters(
                model_parameters,
                SEEDREAM_MODEL_PARAMETER_NAMES,
            )
            max_images = model_parameters.get("max_images")
            if max_images is not None:
                seedream_parameters["sequential_image_generation_options"] = (
                    build_model(
                        SequentialImageGenerationOptions,
                        "Invalid Seedream sequential image options",
                        max_images=max_images,
                    )
                )
            if (
                platform
                and platform.supports_web_search
                and model_parameters.get("web_search")
            ):
                seedream_parameters["tools"] = [WebSearchTool()]
            images = self.extract_seedream_images(prompt_messages)
            if images:
                seedream_parameters["image"] = images[0] if len(images) == 1 else images
            request_model = build_model(
                SeedreamGenerationRequest,
                "Invalid Seedream generation request",
                model=model,
                prompt=prompt,
                **seedream_parameters,
            )
            try:
                generation_response = self.request_model(
                    credentials=ark_credentials,
                    method="POST",
                    path="images/generations",
                    payload=request_model,
                    response_model=SeedreamGenerationResponse,
                    response_context="Invalid Seedream generation response",
                )
            except ArkHTTPError as error:
                return LLMPollingResult(
                    status=LLMPollingStatus.FAILED,
                    error=format_provider_error(error),
                )
            except InvokeError as error:
                return failed_polling_result_from_validation(error)
            return self.seedream_polling_result_from_response(
                model=model,
                credentials=ark_credentials,
                prompt_messages=prompt_messages,
                response=generation_response,
                output_format=request_model.output_format,
            )

        raise NotImplementedError(f"Model `{model}` does not support polling.")

    def _check_polling(
        self,
        model: str,
        credentials: dict,
        plugin_state: dict[str, Any],
        user: str | None = None,
        *,
        workflow_run_id: str,
        node_id: str,
    ) -> LLMPollingResult:
        del user, workflow_run_id, node_id
        ark_credentials = parse_model(
            ArkCredentials,
            credentials,
            "Invalid Ark credentials",
        )
        if is_seedance_model(model):
            try:
                state = parse_model(
                    SeedancePollingState,
                    plugin_state,
                    "Invalid Seedance polling state",
                )
            except InvokeError as error:
                return LLMPollingResult(
                    status=LLMPollingStatus.FAILED,
                    error=str(error),
                )
            task_id = state.task_id
            state_payload = state.to_payload()
            try:
                task_response = self.request_model(
                    credentials=ark_credentials,
                    method="GET",
                    path=f"contents/generations/tasks/{task_id}",
                    response_model=SeedanceTaskResponse,
                    response_context="Invalid Seedance task response",
                )
            except ArkHTTPError as error:
                if is_retryable_http_status(error.status_code):
                    return LLMPollingResult(
                        status=LLMPollingStatus.RUNNING,
                        plugin_state=state_payload,
                        next_check_after_seconds=DEFAULT_POLLING_INTERVAL_SECONDS,
                        expires_after_seconds=DEFAULT_POLLING_EXPIRES_AFTER_SECONDS,
                        max_attempts=DEFAULT_POLLING_MAX_ATTEMPTS,
                    )
                return LLMPollingResult(
                    status=LLMPollingStatus.FAILED,
                    plugin_state=state_payload,
                    error=format_provider_error(error),
                )
            except (URLError, TimeoutError) as error:
                logger.warning("Seedance check request failed: %s", error)
                return LLMPollingResult(
                    status=LLMPollingStatus.RUNNING,
                    plugin_state=state_payload,
                    next_check_after_seconds=DEFAULT_POLLING_INTERVAL_SECONDS,
                    expires_after_seconds=DEFAULT_POLLING_EXPIRES_AFTER_SECONDS,
                    max_attempts=DEFAULT_POLLING_MAX_ATTEMPTS,
                )
            except InvokeError as error:
                return failed_polling_result_from_validation(error)
            return self.seedance_polling_result_from_task(
                model=model,
                credentials=ark_credentials,
                prompt_messages=[],
                task_payload=task_response,
            )

        if is_seedream_model(model):
            return LLMPollingResult(
                status=LLMPollingStatus.FAILED,
                error="Seedream returns a terminal polling result from start_polling.",
            )

        raise NotImplementedError(f"Model `{model}` does not support polling.")

    def seedream_polling_result_from_response(
        self,
        *,
        model: str,
        credentials: ArkCredentials,
        prompt_messages: list[PromptMessage],
        response: SeedreamGenerationResponse,
        output_format: object,
    ) -> LLMPollingResult:
        if response.error:
            return LLMPollingResult(
                status=LLMPollingStatus.FAILED,
                error=format_provider_error(response.error),
            )

        images = response.data
        if images is None:
            return LLMPollingResult(
                status=LLMPollingStatus.FAILED,
                error="Seedream response did not include image data.",
            )

        assistant_contents: list[Any] = []
        image_errors: list[str] = []
        for index, image in enumerate(images):
            if image.error:
                image_errors.append(format_provider_error(image.error))
                continue
            image_url = image.url
            if isinstance(image_url, str) and image_url:
                image_format = guess_format_from_url(
                    image_url,
                    str(output_format or "jpeg"),
                )
                assistant_contents.append(
                    ImagePromptMessageContent(
                        format=image_format,
                        mime_type=guess_image_mime_type(
                            url=image_url,
                            output_format=str(output_format) if output_format else None,
                        ),
                        url=image_url,
                        filename=f"{model}-{index + 1}.{image_format}",
                    )
                )
                continue

            b64_json = image.b64_json
            if isinstance(b64_json, str) and b64_json:
                image_format = str(output_format or "jpeg")
                assistant_contents.append(
                    ImagePromptMessageContent(
                        format=image_format,
                        mime_type=guess_image_mime_type(output_format=image_format),
                        base64_data=b64_json,
                        filename=f"{model}-{index + 1}.{image_format}",
                    )
                )

        if not assistant_contents:
            error = (
                image_errors[0]
                if image_errors
                else "Seedream response did not include generated images."
            )
            return LLMPollingResult(
                status=LLMPollingStatus.FAILED,
                error=error,
            )

        return LLMPollingResult(
            status=LLMPollingStatus.SUCCEEDED,
            result=LLMResult(
                model=model,
                prompt_messages=prompt_messages,
                message=AssistantPromptMessage(content=assistant_contents),
                usage=self.usage_from_provider_payload(
                    model=model,
                    credentials=credentials,
                    usage_payload=response.usage,
                    completion_token_keys=("output_tokens",),
                ),
            ),
        )

    def _invoke(
        self,
        model: str,
        credentials: dict[str, Any],
        prompt_messages: list[PromptMessage],
        model_parameters: dict[str, Any],
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult | Generator[LLMResultChunk, None, None]:
        ark_credentials = parse_model(
            ArkCredentials,
            credentials,
            "Invalid Ark credentials",
        )
        credentials_payload = ark_credentials.to_payload()
        client = Ark(
            base_url=ark_credentials.api_endpoint_host,
            api_key=ark_credentials.ark_api_key,
        )

        chat_request = build_chat_completion_request(
            model=model,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            user=user,
        )

        def _handle_stream() -> Generator[LLMResultChunk, None, None]:
            try:
                stream_request = chat_request.model_copy(
                    update={
                        "stream_options": chat_stream_options_from_parameters(
                            model_parameters
                        )
                    }
                )

                resp = cast(
                    Stream[ChatCompletionChunk],
                    client.chat.completions.create(
                        **stream_request.to_payload(),
                        stream=True,
                    ),
                )

                aggregated_tool_calls: dict[int, AssistantPromptMessage.ToolCall] = {}
                usage_obj = None
                is_reasoning_started = False

                chunk_index = 0

                final_chunk = LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=""),
                    ),
                )

                for chunk in resp:
                    if len(chunk.choices) == 0:
                        if chunk.usage:
                            usage_obj = chunk.usage
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta

                    delta_content = delta.content or ""
                    delta_reasoning = delta.reasoning_content
                    processed_content, is_reasoning_started = wrap_thinking(
                        delta_content, delta_reasoning, is_reasoning_started
                    )

                    if delta.tool_calls:
                        for tool_call_chunk in delta.tool_calls:
                            idx = tool_call_chunk.index
                            existing = aggregated_tool_calls.get(idx)
                            if existing is None:
                                fn_name = ""
                                fn_args = ""
                                if tool_call_chunk.function:
                                    fn_name = tool_call_chunk.function.name or ""
                                    fn_args = tool_call_chunk.function.arguments or ""
                                aggregated_tool_calls[idx] = (
                                    AssistantPromptMessage.ToolCall(
                                        id=tool_call_chunk.id or "",
                                        type=tool_call_chunk.type or "function",
                                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                            name=fn_name,
                                            arguments=fn_args,
                                        ),
                                    )
                                )
                            else:
                                if tool_call_chunk.id:
                                    existing.id = tool_call_chunk.id
                                if tool_call_chunk.type:
                                    existing.type = tool_call_chunk.type
                                if tool_call_chunk.function:
                                    if tool_call_chunk.function.name:
                                        existing.function.name = (
                                            tool_call_chunk.function.name
                                        )
                                    if tool_call_chunk.function.arguments:
                                        existing.function.arguments += (
                                            tool_call_chunk.function.arguments
                                        )

                    if choice.finish_reason == "tool_calls" and aggregated_tool_calls:
                        tool_calls = [
                            aggregated_tool_calls[i]
                            for i in sorted(aggregated_tool_calls)
                            if aggregated_tool_calls[i] is not None
                        ]
                        yield LLMResultChunk(
                            model=chunk.model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=chunk_index,
                                message=AssistantPromptMessage(
                                    content="", tool_calls=tool_calls
                                ),
                                finish_reason="tool_calls",
                            ),
                        )
                        chunk_index += 1
                        continue

                    if processed_content:
                        yield LLMResultChunk(
                            model=chunk.model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=chunk_index,
                                message=AssistantPromptMessage(
                                    content=processed_content
                                ),
                            ),
                        )
                        chunk_index += 1

                    if (
                        choice.finish_reason is not None
                        and choice.finish_reason != "tool_calls"
                    ):
                        final_chunk = LLMResultChunk(
                            model=chunk.model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=chunk_index,
                                message=AssistantPromptMessage(content=""),
                                finish_reason=choice.finish_reason,
                            ),
                        )

                if usage_obj is not None:
                    try:
                        usage = self._calc_response_usage(
                            model=model,
                            credentials=credentials_payload,
                            prompt_tokens=usage_obj.prompt_tokens,
                            completion_tokens=usage_obj.completion_tokens,
                        )
                        final_chunk.delta.usage = usage
                    except Exception:
                        pass

                yield final_chunk
            except Exception as e:
                raise InvokeError(str(e))

        def _handle_block() -> LLMResult:
            try:
                resp = cast(
                    ChatCompletion,
                    client.chat.completions.create(
                        **chat_request.to_payload(),
                        stream=False,
                    ),
                )
                choice = resp.choices[0]
                msg = choice.message

                tool_calls = []
                if msg.tool_calls:
                    for call in msg.tool_calls:
                        tool_calls.append(
                            AssistantPromptMessage.ToolCall(
                                id=call.id,
                                type=call.type,
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name=call.function.name,
                                    arguments=call.function.arguments,
                                ),
                            )
                        )

                content = msg.content or ""
                reasoning_content = msg.reasoning_content
                if reasoning_content:
                    content = f"<think>\n{reasoning_content}\n</think>\n" + (
                        content or ""
                    )

                usage_obj = resp.usage
                if usage_obj is None:
                    prompt_tokens = self.get_num_tokens(
                        model, credentials_payload, prompt_messages, tools
                    )
                    completion_tokens = max(1, len(content) // 4)
                else:
                    prompt_tokens = usage_obj.prompt_tokens
                    completion_tokens = usage_obj.completion_tokens

                usage = self._calc_response_usage(
                    model=model,
                    credentials=credentials_payload,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

                return LLMResult(
                    model=model,
                    prompt_messages=prompt_messages,
                    message=AssistantPromptMessage(
                        content=content, tool_calls=tool_calls
                    ),
                    usage=usage,
                )
            except Exception as e:
                raise InvokeError(str(e))

        return _handle_stream() if stream else _handle_block()
