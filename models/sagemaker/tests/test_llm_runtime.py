import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import EventStreamError
from dify_plugin.entities.model.message import UserPromptMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.llm import llm as llm_module
from models.llm.llm import SageMakerLargeLanguageModel, inference


def test_llm_uses_runtime_client_with_configured_credentials(monkeypatch):
    session = MagicMock()
    session.client.return_value.invoke_endpoint.return_value = {
        "Body": io.BytesIO(b"reply")
    }
    session_factory = MagicMock(return_value=session)
    monkeypatch.setattr(llm_module.boto3, "Session", session_factory)
    llm = SageMakerLargeLanguageModel([])
    llm._handle_chat_generate_response = lambda **kwargs: kwargs["resp"]

    result = llm._invoke(
        "model",
        {
            "aws_access_key_id": "access",
            "aws_secret_access_key": "secret",
            "aws_region": "us-east-1",
            "sagemaker_endpoint": "endpoint",
        },
        [UserPromptMessage(content="Hi")],
        {},
        stream=False,
    )

    assert result == b"reply"
    session_factory.assert_called_once_with(
        aws_access_key_id="access",
        aws_secret_access_key="secret",
        region_name="us-east-1",
    )
    session.client.assert_called_once_with("sagemaker-runtime")


def test_runtime_invocation_preserves_payload_bytes_and_stream_errors():
    client = MagicMock()
    body = io.BytesIO(b'{"choices": []}')
    client.invoke_endpoint.return_value = {"Body": body}
    args = {
        "client": client,
        "endpoint_name": "endpoint",
        "messages": [{"role": "user", "content": "Hi"}],
        "params": {"max_new_tokens": 32},
        "stop": ["END"],
        "model_id": "model",
    }

    assert inference(**args) == b'{"choices": []}'
    assert body.closed
    request = client.invoke_endpoint.call_args.kwargs
    assert request["EndpointName"] == "endpoint"
    assert request["ContentType"] == "application/json"
    assert json.loads(request["Body"]) == {
        "model": "model",
        "messages": args["messages"],
        "stream": False,
        "max_tokens": 32,
        "temperature": 0.1,
        "top_p": 0.9,
        "stop": ["END"],
    }

    events = MagicMock()
    events.__iter__.return_value = iter(
        [{"PayloadPart": {"Bytes": b"one"}}, {"PayloadPart": {"Bytes": b"two"}}]
    )
    client.invoke_endpoint_with_response_stream.return_value = {"Body": events}
    assert list(inference(**args, stream=True)) == [b"one", b"two"]
    assert (
        json.loads(
            client.invoke_endpoint_with_response_stream.call_args.kwargs["Body"]
        )["stream"]
        is True
    )
    events.close.assert_called_once()

    events.reset_mock()
    events.__iter__.side_effect = EventStreamError(
        {"Error": {"Code": "ModelStreamError", "Message": "model failed"}},
        "InvokeEndpointWithResponseStream",
    )
    with pytest.raises(EventStreamError, match="model failed"):
        list(inference(**args, stream=True))
    events.close.assert_called_once()
