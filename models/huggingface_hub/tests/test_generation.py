import json

from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import UserPromptMessage
import httpx2
import pytest

from models.llm.llm import HuggingfaceHubLargeLanguageModel


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("stop", [None, ["END"]])
def test_generation_sends_stop_sequences_and_reads_response(monkeypatch, stream, stop):
    requests = []
    token = {"id": 1, "text": "ok", "logprob": 0.0, "special": False}
    details = {"finish_reason": "stop_sequence", "generated_tokens": 1}

    def respond(request):
        requests.append(json.loads(request.content))
        if stream:
            event = {
                "index": 0,
                "token": token,
                "generated_text": "ok",
                "details": {**details, "input_length": 1},
            }
            return httpx2.Response(200, text=f"data: {json.dumps(event)}\n\n")
        return httpx2.Response(
            200,
            json=[
                {
                    "generated_text": "ok",
                    "details": {**details, "prefill": [], "tokens": [token]},
                }
            ],
        )

    monkeypatch.setattr(HuggingfaceHubLargeLanguageModel, "get_num_tokens", lambda *args: 1)
    monkeypatch.setattr(
        HuggingfaceHubLargeLanguageModel,
        "_calc_response_usage",
        lambda *args: LLMUsage.empty_usage(),
    )
    with httpx2.Client(transport=httpx2.MockTransport(respond)) as client:
        monkeypatch.setattr("huggingface_hub.inference._client.get_session", lambda: client)
        result = HuggingfaceHubLargeLanguageModel([])._invoke(
            model="test-model",
            credentials={
                "huggingfacehub_api_token": "test-token",
                "huggingfacehub_api_type": "inference_endpoints",
                "huggingfacehub_endpoint_url": "https://example.invalid/generate",
            },
            prompt_messages=[UserPromptMessage(content="Hello")],
            model_parameters={"max_new_tokens": 10},
            stop=stop,
            stream=stream,
        )
        content = (
            "".join(chunk.delta.message.content for chunk in result)
            if stream
            else result.message.content
        )

    assert content == "ok"
    assert len(requests) == 1
    assert requests[0]["inputs"] == "Hello"
    assert requests[0]["parameters"].get("stop") == stop
    assert requests[0]["stream"] is stream
