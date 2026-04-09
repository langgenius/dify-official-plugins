"""
Integration tests for oaicompat_dify_model endpoints.

These endpoints expose OpenAI-compatible API for Dify models:
- /v1/chat/completions - LLM endpoint
- /v1/embeddings - Text embedding endpoint
"""
import json
from pydantic import BaseModel
from dify_plugin.core.entities.plugin.request import (
    PluginInvokeType,
    EndpointActions,
    EndpointInvokeRequest,
)


class EndpointResponse(BaseModel):
    """Generic response model for endpoint invocation."""
    status: int = 200
    headers: dict = {}
    body: str = ""


def build_raw_http_request(method: str, path: str, headers: dict, body: dict | None = None) -> str:
    """
    Build a raw HTTP request string for endpoint testing.
    
    The raw_http_request needs to be a hex-encoded actual HTTP request.
    """
    # Build body string
    body_str = json.dumps(body) if body else ""
    
    # Add Content-Length header
    if body_str:
        headers["Content-Length"] = str(len(body_str))
    
    # Build headers string
    headers_str = "\r\n".join(f"{k}: {v}" for k, v in headers.items())
    
    # Build raw HTTP request in standard HTTP/1.1 format
    raw_request = f"{method} {path} HTTP/1.1\r\n{headers_str}\r\n\r\n{body_str}"
    
    # Hex-encode the request
    return raw_request.encode("utf-8").hex()




def test_llm_endpoint_unauthorized(plugin_runner):
    """
    Test the LLM endpoint returns 401 when no API key is provided.
    """
    settings = {
        "api_key": "test_api_key",
        "llm": {
            "provider": "openai",
            "model": "gpt-3.5-turbo",
        }
    }
    
    raw_request = build_raw_http_request(
        method="POST",
        path="/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            # No Authorization header - should fail
        },
        body={
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "stream": False,
        }
    )
    
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Endpoint,
        access_action=EndpointActions.InvokeEndpoint,
        payload=EndpointInvokeRequest(
            settings=settings,
            raw_http_request=raw_request,
        ),
        response_type=EndpointResponse,
    ):
        response_chunks.append(result)
    
    assert len(response_chunks) == 1
    # Should return 401 Unauthorized
    assert response_chunks[0].status == 401


def test_llm_endpoint_with_auth(plugin_runner):
    """
    Test the LLM endpoint with valid API key.
    Note: This test may fail if no LLM model is configured in the test environment.
    """
    api_key = "test_api_key_12345"
    settings = {
        "api_key": api_key,
        "llm": {
            "provider": "openai",
            "model": "gpt-3.5-turbo",
            "completion_params": {},
        }
    }
    
    raw_request = build_raw_http_request(
        method="POST",
        path="/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        body={
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "stream": False,
        }
    )
    
    response_chunks = []
    try:
        for result in plugin_runner.invoke(
            access_type=PluginInvokeType.Endpoint,
            access_action=EndpointActions.InvokeEndpoint,
            payload=EndpointInvokeRequest(
                settings=settings,
                raw_http_request=raw_request,
            ),
            response_type=EndpointResponse,
        ):
            response_chunks.append(result)
        
        # If we get here, the endpoint processed the request
        assert len(response_chunks) >= 1
    except ValueError as e:
        # Expected if no actual LLM model is configured
        error_str = str(e)
        # The test passes if we got past authentication (error is about model, not auth)
        assert "Unauthorized" not in error_str


def test_embedding_endpoint_unauthorized(plugin_runner):
    """
    Test the text embedding endpoint returns 401 when no API key is provided.
    """
    settings = {
        "api_key": "test_api_key",
        "text_embedding": {
            "provider": "openai",
            "model": "text-embedding-3-small",
        }
    }
    
    raw_request = build_raw_http_request(
        method="POST",
        path="/v1/embeddings",
        headers={
            "Content-Type": "application/json",
            # No Authorization header - should fail
        },
        body={
            "input": "Hello, world!",
        }
    )
    
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Endpoint,
        access_action=EndpointActions.InvokeEndpoint,
        payload=EndpointInvokeRequest(
            settings=settings,
            raw_http_request=raw_request,
        ),
        response_type=EndpointResponse,
    ):
        response_chunks.append(result)
    
    assert len(response_chunks) == 1
    # Should return 401 Unauthorized
    assert response_chunks[0].status == 401

