from dify_plugin.integration.run import (
    PluginRunner,
)

from tests.models.z_mockserver.openai import OPENAI_MOCK_SERVER_PORT
from dify_plugin.config.integration_config import IntegrationConfig
from dify_plugin.core.entities.plugin.request import (
    ModelActions,
    ModelInvokeLLMRequest,
    ModelInvokeModerationRequest,
    ModelInvokeSpeech2TextRequest,
    ModelInvokeTextEmbeddingRequest,
    ModelInvokeTTSRequest,
    PluginInvokeType,
)
from dify_plugin.entities.model.moderation import ModerationResult
from dify_plugin.entities.model.speech2text import Speech2TextResult
from dify_plugin.entities.model.text_embedding import TextEmbeddingResult
from dify_plugin.entities.model.tts import TTSResult
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    UserPromptMessage,
)


def test_openai_blocking(mock_server, plugin_runner):
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeLLM,
        payload=ModelInvokeLLMRequest(
            prompt_messages=[
                UserPromptMessage(content="Hello, world!"),
            ],
            user_id="",
            provider="openai",
            model_type=ModelType.LLM,
            model="gpt-3.5-turbo",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
            model_parameters={},
            stop=[],
            tools=[],
            stream=False,
        ),
        response_type=LLMResultChunk,
    ):
        assert result.delta.message.content == "Hello, world!"


def test_openai_streaming(mock_server, plugin_runner):
    chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeLLM,
        payload=ModelInvokeLLMRequest(
            prompt_messages=[
                UserPromptMessage(content="Hello, world!"),
            ],
            user_id="",
            provider="openai",
            model_type=ModelType.LLM,
            model="gpt-3.5-turbo",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
            model_parameters={},
            stop=[],
            tools=[],
            stream=True,
        ),
        response_type=LLMResultChunk,
    ):
        chunks.append(result)
    
    # Verify we received streaming chunks
    assert len(chunks) > 0, "Should receive at least one chunk"
    
    # Collect all content from chunks
    full_content = "".join(
        chunk.delta.message.content 
        for chunk in chunks 
        if chunk.delta.message.content
    )
    
    assert full_content == "Hello, world!"


def test_openai_with_system_message(mock_server, plugin_runner):
    """Test with system message"""
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeLLM,
        payload=ModelInvokeLLMRequest(
            prompt_messages=[
                SystemPromptMessage(content="You are a helpful assistant."),
                UserPromptMessage(content="Hello, world!"),
            ],
            user_id="",
            provider="openai",
            model_type=ModelType.LLM,
            model="gpt-3.5-turbo",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
            model_parameters={},
            stop=[],
            tools=[],
            stream=False,
        ),
        response_type=LLMResultChunk,
    ):
        assert result.delta.message.content == "Hello, world!"


def test_openai_multi_turn_conversation(mock_server, plugin_runner):
    """Test multi-turn conversation"""
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeLLM,
        payload=ModelInvokeLLMRequest(
            prompt_messages=[
                SystemPromptMessage(content="You are a helpful assistant."),
                UserPromptMessage(content="Hi there!"),
                AssistantPromptMessage(content="Hello! How can I help you?"),
                UserPromptMessage(content="Hello, world!"),
            ],
            user_id="",
            provider="openai",
            model_type=ModelType.LLM,
            model="gpt-3.5-turbo",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
            model_parameters={},
            stop=[],
            tools=[],
            stream=False,
        ),
        response_type=LLMResultChunk,
    ):
        assert result.delta.message.content == "Hello, world!"


def test_openai_with_temperature(mock_server, plugin_runner):
    """Test with temperature parameter"""
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeLLM,
        payload=ModelInvokeLLMRequest(
            prompt_messages=[
                UserPromptMessage(content="Hello, world!"),
            ],
            user_id="",
            provider="openai",
            model_type=ModelType.LLM,
            model="gpt-3.5-turbo",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
            model_parameters={"temperature": 0.7},
            stop=[],
            tools=[],
            stream=False,
        ),
        response_type=LLMResultChunk,
    ):
        assert result.delta.message.content == "Hello, world!"


def test_openai_with_max_tokens(mock_server, plugin_runner):
    """Test with max_tokens parameter"""
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeLLM,
        payload=ModelInvokeLLMRequest(
            prompt_messages=[
                UserPromptMessage(content="Hello, world!"),
            ],
            user_id="",
            provider="openai",
            model_type=ModelType.LLM,
            model="gpt-3.5-turbo",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
            model_parameters={"max_tokens": 100},
            stop=[],
            tools=[],
            stream=False,
        ),
        response_type=LLMResultChunk,
    ):
        assert result.delta.message.content == "Hello, world!"


def test_openai_with_tools(mock_server, plugin_runner):
    """Test with function/tool calling"""
    tools = [
        PromptMessageTool(
            name="get_weather",
            description="Get the current weather for a location",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city name, e.g. San Francisco",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                    },
                },
                "required": ["location"],
            },
        )
    ]
    
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeLLM,
        payload=ModelInvokeLLMRequest(
            prompt_messages=[
                UserPromptMessage(content="Hello, world!"),
            ],
            user_id="",
            provider="openai",
            model_type=ModelType.LLM,
            model="gpt-3.5-turbo",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
            model_parameters={},
            stop=[],
            tools=tools,
            stream=False,
        ),
        response_type=LLMResultChunk,
    ):
        # With tools, the response might be a tool call or regular message
        assert result.delta.message is not None


def test_openai_streaming_with_parameters(mock_server, plugin_runner):
    """Test streaming with multiple parameters"""
    chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeLLM,
        payload=ModelInvokeLLMRequest(
            prompt_messages=[
                SystemPromptMessage(content="You are a helpful assistant."),
                UserPromptMessage(content="Hello, world!"),
            ],
            user_id="test_user",
            provider="openai",
            model_type=ModelType.LLM,
            model="gpt-3.5-turbo",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
            model_parameters={
                "temperature": 0.5,
                "max_tokens": 150,
            },
            stop=[],
            tools=[],
            stream=True,
        ),
        response_type=LLMResultChunk,
    ):
        chunks.append(result)
    
    assert len(chunks) > 0
    
    full_content = "".join(
        chunk.delta.message.content 
        for chunk in chunks 
        if chunk.delta.message.content
    )
    
    assert full_content == "Hello, world!"


def test_openai_moderation(mock_server, plugin_runner):
    """Test moderation"""
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeModeration,
        payload=ModelInvokeModerationRequest(
            text="I want to kill them.",
            user_id="test_user",
            provider="openai",
            model_type=ModelType.MODERATION,
            model="text-moderation-stable",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
        ),
        response_type=ModerationResult,
    ):
        assert result.result is False


def test_openai_text_embedding(mock_server, plugin_runner):
    """Test text embedding"""
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeTextEmbedding,
        payload=ModelInvokeTextEmbeddingRequest(
            texts=["Hello, world!"],
            user_id="test_user",
            provider="openai",
            model_type=ModelType.TEXT_EMBEDDING,
            model="text-embedding-3-small",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
        ),
        response_type=TextEmbeddingResult,
    ):
        assert len(result.embeddings) == 1
        assert len(result.embeddings[0]) == 1536
        assert result.usage.total_tokens == 10


def test_openai_tts(mock_server, plugin_runner):
    """Test text to speech"""
    chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeTTS,
        payload=ModelInvokeTTSRequest(
            content_text="Hello, world!",
            voice="alloy",
            user_id="test_user",
            tenant_id="test_tenant",
            provider="openai",
            model_type=ModelType.TTS,
            model="tts-1",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
        ),
        response_type=TTSResult,
    ):
        chunks.append(result)

    assert len(chunks) > 0


def test_openai_speech2text(mock_server, plugin_runner, tmp_path):
    """Test speech to text"""
    # Create dummy audio file
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"dummy audio content")

    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeSpeech2Text,
        payload=ModelInvokeSpeech2TextRequest(
            file=audio_file.read_bytes().hex(),
            user_id="test_user",
            provider="openai",
            model_type=ModelType.SPEECH2TEXT,
            model="whisper-1",
            credentials={
                "openai_api_base": f"http://localhost:{OPENAI_MOCK_SERVER_PORT}",
                "openai_api_key": "test",
            },
        ),
        response_type=Speech2TextResult,
    ):
        assert result.result == "Hello, world!"

