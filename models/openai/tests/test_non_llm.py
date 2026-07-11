from decimal import Decimal
from io import BytesIO
from math import sqrt
from types import SimpleNamespace

import openai
import pytest
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.text_embedding import EmbeddingUsage
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from models.common_openai import _CommonOpenAI
from models.moderation.moderation import OpenAIModerationModel
from models.speech2text.speech2text import OpenAISpeech2TextModel
from models.text_embedding.text_embedding import (
    OpenAITextEmbeddingModel,
    _merge_embeddings,
    _normalize,
)
from models.tts.tts import OpenAIText2SpeechModel
from provider.openai import OpenAIProvider


def _instance(model_class):
    return object.__new__(model_class)


def _embedding_usage(tokens: int) -> EmbeddingUsage:
    return EmbeddingUsage(
        tokens=tokens,
        total_tokens=tokens,
        unit_price=Decimal(0),
        price_unit=Decimal(0),
        total_price=Decimal(0),
        currency="USD",
        latency=0,
    )


@pytest.mark.parametrize(
    ("credentials", "expected"),
    [
        ({"openai_api_key": "key"}, {"api_key": "key"}),
        (
            {
                "openai_api_key": "key",
                "openai_api_base": "https://proxy.example.com/",
                "openai_organization": "org_123",
            },
            {
                "api_key": "key",
                "base_url": "https://proxy.example.com/v1",
                "organization": "org_123",
            },
        ),
        (
            {
                "openai_api_key": "key",
                "openai_api_base": "https://proxy.example.com/v1/",
                "openai_organization": "",
            },
            {"api_key": "key", "base_url": "https://proxy.example.com/v1"},
        ),
    ],
)
def test_credentials_are_minimal_and_base_url_has_one_v1(credentials, expected):
    assert _CommonOpenAI()._to_credential_kwargs(credentials) == expected


def test_common_error_transform_preserves_plugin_errors_and_delegates_others(mocker):
    sentinel = InvokeConnectionError("mapped")

    class Parent:
        def _transform_invoke_error(self, error):
            return sentinel

    class Subject(_CommonOpenAI, Parent):
        pass

    parent_transform = mocker.patch.object(
        Parent, "_transform_invoke_error", autospec=True, return_value=sentinel
    )
    plugin_error = InvokeBadRequestError("already mapped")
    runtime_error = RuntimeError("raw")
    subject = Subject()

    assert subject._transform_invoke_error(plugin_error) is plugin_error
    assert subject._transform_invoke_error(runtime_error) is sentinel
    parent_transform.assert_called_once_with(subject, runtime_error)


@pytest.mark.parametrize(
    ("target", "sources"),
    [
        (InvokeConnectionError, (openai.APIConnectionError, openai.APITimeoutError)),
        (InvokeServerUnavailableError, (openai.InternalServerError,)),
        (InvokeRateLimitError, (openai.RateLimitError,)),
        (
            InvokeAuthorizationError,
            (openai.AuthenticationError, openai.PermissionDeniedError),
        ),
        (
            InvokeBadRequestError,
            (
                openai.BadRequestError,
                openai.NotFoundError,
                openai.UnprocessableEntityError,
                openai.APIError,
            ),
        ),
    ],
)
def test_common_error_mapping_covers_openai_failures(target, sources):
    mapping: dict[type[InvokeError], list[type[Exception]]] = (
        _CommonOpenAI()._invoke_error_mapping
    )

    assert set(sources) <= set(mapping[target])


def test_embedding_chunks_batches_and_merges(mocker):
    model = _instance(OpenAITextEmbeddingModel)
    mocker.patch.object(model, "_get_context_size", return_value=2)
    mocker.patch.object(model, "_get_max_chunks", return_value=2)
    usage = _embedding_usage(8)
    calculate_usage = mocker.patch.object(
        model, "_calc_response_usage", return_value=usage
    )
    encoding = mocker.Mock()
    encoding.encode.side_effect = {
        "long": [1, 2, 3, 4, 5],
        "short": [6, 7, 8],
    }.get
    encoding_for_model = mocker.patch(
        "models.text_embedding.text_embedding.tiktoken.encoding_for_model",
        return_value=encoding,
    )
    client = mocker.Mock()
    openai_client = mocker.patch(
        "models.text_embedding.text_embedding.OpenAI", return_value=client
    )
    vectors = {
        (1, 2): [1.0, 0.0],
        (3, 4): [0.0, 1.0],
        (5,): [1.0, 1.0],
        (6, 7): [2.0, 0.0],
        (8,): [0.0, 1.0],
    }

    def embed(*, model, client, texts, user=None):
        return [vectors[tuple(tokens)] for tokens in texts], sum(map(len, texts))

    invoke = mocker.patch.object(model, "_embedding_invoke", side_effect=embed)

    result = model._invoke(
        "text-embedding-3-small",
        {"openai_api_key": "key"},
        ["long", "short"],
        user="user-1",
    )

    assert result.embeddings[0] == pytest.approx([1 / sqrt(2), 1 / sqrt(2)])
    assert result.embeddings[1] == pytest.approx([4 / sqrt(17), 1 / sqrt(17)])
    assert result.usage is usage
    assert [call.kwargs["texts"] for call in invoke.call_args_list] == [
        [[1, 2], [3, 4]],
        [[5], [6, 7]],
        [[8]],
    ]
    assert all(call.kwargs["user"] == "user-1" for call in invoke.call_args_list)
    encoding_for_model.assert_called_once_with("text-embedding-3-small")
    openai_client.assert_called_once_with(api_key="key")
    calculate_usage.assert_called_once_with(
        model="text-embedding-3-small",
        credentials={"openai_api_key": "key"},
        tokens=8,
    )


@pytest.mark.parametrize("texts", [[], [""], ["valid", ""]])
def test_embedding_rejects_empty_input(mocker, texts):
    model = _instance(OpenAITextEmbeddingModel)
    openai_client = mocker.patch("models.text_embedding.text_embedding.OpenAI")

    with pytest.raises(InvokeBadRequestError, match="must not be empty"):
        model._invoke("text-embedding-3-small", {"openai_api_key": "key"}, texts)

    openai_client.assert_not_called()


def test_embedding_unknown_model_uses_cl100k_tokenizer(mocker):
    model = _instance(OpenAITextEmbeddingModel)
    fallback = mocker.Mock()
    fallback.encode.side_effect = lambda text: list(range(len(text)))
    mocker.patch(
        "models.text_embedding.text_embedding.tiktoken.encoding_for_model",
        side_effect=KeyError("unknown"),
    )
    get_encoding = mocker.patch(
        "models.text_embedding.text_embedding.tiktoken.get_encoding",
        return_value=fallback,
    )

    assert model.get_num_tokens("future-embedding", {}, ["", "abc"]) == [0, 3]
    get_encoding.assert_called_once_with("cl100k_base")


def test_embedding_sdk_requests_float_vectors(mocker):
    model = _instance(OpenAITextEmbeddingModel)
    client = mocker.Mock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.25, 0.75])],
        usage=SimpleNamespace(total_tokens=4),
    )

    embeddings, tokens = model._embedding_invoke(
        "text-embedding-3-small", client, [[1, 2, 3, 4]], user="user-1"
    )

    assert embeddings == [[0.25, 0.75]]
    assert tokens == 4
    client.embeddings.create.assert_called_once_with(
        input=[[1, 2, 3, 4]],
        model="text-embedding-3-small",
        encoding_format="float",
        user="user-1",
    )


@pytest.mark.parametrize(
    "operation",
    [
        lambda: _normalize([0.0, 0.0]),
        lambda: _normalize([float("inf"), 1.0]),
        lambda: _normalize([float("nan"), 1.0]),
        lambda: _merge_embeddings([], []),
        lambda: _merge_embeddings([[1.0, 0.0]], [0]),
        lambda: _merge_embeddings([[1.0], [0.0, 1.0]], [1, 1]),
        lambda: _merge_embeddings([[1.0], [1.0]], [1]),
    ],
)
def test_embedding_rejects_invalid_vectors(operation):
    with pytest.raises(ValueError):
        operation()


@pytest.mark.parametrize(
    ("voice", "default_voice", "expected_voice", "uses_default"),
    [
        ("nova", "alloy", "nova", False),
        ("bad", "nova", "nova", True),
        ("bad", None, "alloy", True),
    ],
)
def test_tts_keeps_valid_voice_or_falls_back(
    mocker, voice, default_voice, expected_voice, uses_default
):
    model = _instance(OpenAIText2SpeechModel)
    mocker.patch.object(
        model,
        "get_tts_model_voices",
        return_value=[{"value": "alloy"}, {"value": "nova"}],
    )
    get_default = mocker.patch.object(
        model, "_get_model_default_voice", return_value=default_voice
    )
    expected = iter([b"audio"])
    invoke = mocker.patch.object(model, "_tts_invoke_streaming", return_value=expected)

    assert (
        model._invoke("tts-1", "tenant", {"openai_api_key": "key"}, "hello", voice)
        is expected
    )
    assert invoke.call_args.kwargs["voice"] == expected_voice
    assert get_default.called is uses_default


def test_tts_rejects_model_without_voices(mocker):
    model = _instance(OpenAIText2SpeechModel)
    mocker.patch.object(model, "get_tts_model_voices", return_value=[])

    with pytest.raises(InvokeBadRequestError, match="No voices"):
        model._invoke("tts-1", "tenant", {"openai_api_key": "key"}, "hello", "")


@pytest.mark.parametrize("content", ["", " \n\t"])
def test_tts_rejects_empty_text(content):
    model = _instance(OpenAIText2SpeechModel)

    with pytest.raises(InvokeBadRequestError, match="must not be empty"):
        model._invoke("tts-1", "tenant", {}, content, "alloy")


def test_tts_sentences_keep_order_and_split_long_segments(mocker):
    model = _instance(OpenAIText2SpeechModel)
    mocker.patch.object(model, "_get_model_word_limit", return_value=4)
    split = mocker.patch.object(
        model, "_split_text_into_sentences", return_value=[" one ", "abcdefghi"]
    )

    assert list(model._sentences("tts-1", {}, "source")) == [
        "one",
        "abcd",
        "efgh",
        "i",
    ]
    split.assert_called_once_with("source", max_length=4)


def test_tts_stream_closes_every_sdk_response_context(mocker):
    model = _instance(OpenAIText2SpeechModel)
    mocker.patch.object(model, "_sentences", return_value=iter(["one", "two"]))
    mocker.patch.object(model, "_get_model_audio_type", return_value="mp3")
    contexts = [mocker.MagicMock(), mocker.MagicMock()]
    responses = [mocker.Mock(), mocker.Mock()]
    responses[0].iter_bytes.return_value = iter([b"a", b"b"])
    responses[1].iter_bytes.return_value = iter([b"c"])
    for context, response in zip(contexts, responses, strict=True):
        context.__enter__.return_value = response
    client = mocker.Mock()
    create = client.audio.speech.with_streaming_response.create
    create.side_effect = contexts
    mocker.patch("models.tts.tts.OpenAI", return_value=client)

    assert list(
        model._tts_invoke_streaming("tts-1", {"openai_api_key": "key"}, "x", "alloy")
    ) == [
        b"a",
        b"b",
        b"c",
    ]
    assert [call.kwargs["input"] for call in create.call_args_list] == ["one", "two"]
    for context in contexts:
        context.__exit__.assert_called_once_with(None, None, None)


def test_tts_nonstream_reads_each_segment_once(mocker):
    model = _instance(OpenAIText2SpeechModel)
    mocker.patch.object(model, "_sentences", return_value=iter(["one", "two"]))
    mocker.patch.object(model, "_get_model_audio_type", return_value="wav")
    responses = [mocker.Mock(), mocker.Mock()]
    responses[0].read.return_value = b"a"
    responses[1].read.return_value = b"b"
    client = mocker.Mock()
    client.audio.speech.create.side_effect = responses
    mocker.patch("models.tts.tts.OpenAI", return_value=client)

    assert model._tts_invoke("tts-1", {"openai_api_key": "key"}, "x", "alloy") == b"ab"
    assert [
        call.kwargs["input"] for call in client.audio.speech.create.call_args_list
    ] == [
        "one",
        "two",
    ]
    for response in responses:
        response.read.assert_called_once_with()


def test_tts_stream_closes_context_and_propagates_sdk_error(mocker):
    model = _instance(OpenAIText2SpeechModel)
    mocker.patch.object(model, "_sentences", return_value=iter(["one"]))
    mocker.patch.object(model, "_get_model_audio_type", return_value="mp3")
    error = RuntimeError("stream failed")
    response = mocker.Mock()
    response.iter_bytes.side_effect = error
    context = mocker.MagicMock()
    context.__enter__.return_value = response
    client = mocker.Mock()
    client.audio.speech.with_streaming_response.create.return_value = context
    mocker.patch("models.tts.tts.OpenAI", return_value=client)

    with pytest.raises(RuntimeError) as caught:
        list(
            model._tts_invoke_streaming(
                "tts-1", {"openai_api_key": "key"}, "x", "alloy"
            )
        )

    assert caught.value is error
    exit_args = context.__exit__.call_args.args
    assert exit_args[:2] == (RuntimeError, error)


@pytest.mark.parametrize(
    ("model_name", "extra_parameters"),
    [
        ("whisper-1", {}),
        ("gpt-4o-transcribe", {}),
        (
            "gpt-4o-transcribe-diarize",
            {"chunking_strategy": "auto", "response_format": "diarized_json"},
        ),
    ],
)
def test_speech_to_text_uses_model_specific_parameters(
    mocker, model_name, extra_parameters
):
    model = _instance(OpenAISpeech2TextModel)
    audio = BytesIO(b"audio")
    client = mocker.Mock()
    client.audio.transcriptions.create.return_value = SimpleNamespace(text="hello")
    openai_client = mocker.patch(
        "models.speech2text.speech2text.OpenAI", return_value=client
    )

    assert model._invoke(model_name, {"openai_api_key": "key"}, audio) == "hello"
    openai_client.assert_called_once_with(api_key="key")
    client.audio.transcriptions.create.assert_called_once_with(
        model=model_name, file=audio, **extra_parameters
    )


def test_moderation_batches_and_stops_after_flagged_result(mocker):
    model = _instance(OpenAIModerationModel)
    mocker.patch.object(model, "_get_max_characters_per_chunk", return_value=2)
    mocker.patch.object(model, "_get_max_chunks", return_value=2)
    moderate = mocker.patch.object(
        model,
        "_moderation_invoke",
        side_effect=[
            SimpleNamespace(
                results=[SimpleNamespace(flagged=False), SimpleNamespace(flagged=False)]
            ),
            SimpleNamespace(
                results=[SimpleNamespace(flagged=False), SimpleNamespace(flagged=True)]
            ),
        ],
    )
    client = mocker.Mock()
    mocker.patch("models.moderation.moderation.OpenAI", return_value=client)

    assert model._invoke(
        "omni-moderation-latest", {"openai_api_key": "key"}, "abcdefghij"
    )
    assert [call.kwargs["texts"] for call in moderate.call_args_list] == [
        ["ab", "cd"],
        ["ef", "gh"],
    ]


def test_moderation_empty_text_short_circuits(mocker):
    model = _instance(OpenAIModerationModel)
    mocker.patch.object(model, "_get_max_characters_per_chunk", return_value=2)
    mocker.patch.object(model, "_get_max_chunks", return_value=2)
    moderate = mocker.patch.object(model, "_moderation_invoke")
    mocker.patch("models.moderation.moderation.OpenAI")

    assert (
        model._invoke("omni-moderation-latest", {"openai_api_key": "key"}, "") is False
    )
    moderate.assert_not_called()


@pytest.mark.parametrize(
    ("credentials", "expected_model"),
    [
        ({"openai_api_key": "key"}, "gpt-4o-mini"),
        (
            {"openai_api_key": "key", "validate_model": "gpt-5-mini"},
            "gpt-5-mini",
        ),
    ],
)
def test_provider_validates_default_or_configured_llm(
    mocker, credentials, expected_model
):
    provider = _instance(OpenAIProvider)
    model = mocker.Mock()
    get_model = mocker.patch.object(provider, "get_model_instance", return_value=model)

    provider.validate_provider_credentials(credentials)

    get_model.assert_called_once_with(ModelType.LLM)
    model.validate_credentials.assert_called_once_with(
        model=expected_model, credentials=credentials
    )


def test_provider_does_not_hide_validation_error(mocker):
    provider = _instance(OpenAIProvider)
    error = RuntimeError("validation failed")
    model = mocker.Mock()
    model.validate_credentials.side_effect = error
    mocker.patch.object(provider, "get_model_instance", return_value=model)

    with pytest.raises(RuntimeError) as caught:
        provider.validate_provider_credentials({"openai_api_key": "key"})

    assert caught.value is error
