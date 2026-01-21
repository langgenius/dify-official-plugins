"""
Integration tests for telegram_trigger plugin.

These tests verify the trigger dispatch logic - parsing Telegram webhook
payloads and routing them to the correct events.
"""
import json
from dify_plugin.core.entities.plugin.request import (
    PluginInvokeType,
    TriggerActions,
    TriggerDispatchEventRequest,
    TriggerDispatchResponse,
)


def build_telegram_webhook_request(
    payload: dict,
    headers: dict | None = None,
) -> str:
    """
    Build a hex-encoded HTTP request for Telegram webhook.
    """
    body_str = json.dumps(payload)
    
    default_headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body_str)),
    }
    if headers:
        default_headers.update(headers)
    
    headers_str = "\r\n".join(f"{k}: {v}" for k, v in default_headers.items())
    raw_request = f"POST /webhook HTTP/1.1\r\n{headers_str}\r\n\r\n{body_str}"
    
    return raw_request.encode("utf-8").hex()


def test_dispatch_message_event(plugin_runner):
    """
    Test that a Telegram message webhook payload correctly dispatches
    to the 'message_received' event.
    """
    telegram_payload = {
        "update_id": 123456789,
        "message": {
            "message_id": 1,
            "from": {
                "id": 12345,
                "is_bot": False,
                "first_name": "Test",
                "username": "testuser",
            },
            "chat": {
                "id": 12345,
                "first_name": "Test",
                "username": "testuser",
                "type": "private",
            },
            "date": 1234567890,
            "text": "Hello, bot!",
        }
    }
    
    raw_request = build_telegram_webhook_request(telegram_payload)
    
    subscription = {
        "endpoint": "https://example.com/webhook",
        "properties": {},  # No secret_token check
        "parameters": {},
        "expires_at": -1,
    }
    
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Trigger,
        access_action=TriggerActions.DispatchTriggerEvent,
        payload=TriggerDispatchEventRequest(
            provider="telegram_trigger",
            subscription=subscription,
            credentials={"bot_token": "test_token"},
            credential_type="api-key",
            raw_http_request=raw_request,
            user_id="test_user",
        ),
        response_type=TriggerDispatchResponse,
    ):
        response_chunks.append(result)
    
    assert len(response_chunks) == 1
    response = response_chunks[0]
    
    # Should dispatch to 'message_received' event
    assert len(response.events) == 1
    assert response.events[0] == "message_received"


def test_dispatch_callback_query_event(plugin_runner):
    """
    Test that a callback query webhook payload dispatches to 
    'callback_query_received' event.
    """
    telegram_payload = {
        "update_id": 123456790,
        "callback_query": {
            "id": "callback123",
            "from": {
                "id": 12345,
                "is_bot": False,
                "first_name": "Test",
            },
            "chat_instance": "chat_instance_123",
            "data": "button_clicked",
        }
    }
    
    raw_request = build_telegram_webhook_request(telegram_payload)
    
    subscription = {
        "endpoint": "https://example.com/webhook",
        "properties": {},
        "parameters": {},
        "expires_at": -1,
    }
    
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Trigger,
        access_action=TriggerActions.DispatchTriggerEvent,
        payload=TriggerDispatchEventRequest(
            provider="telegram_trigger",
            subscription=subscription,
            credentials={"bot_token": "test_token"},
            credential_type="api-key",
            raw_http_request=raw_request,
            user_id="test_user",
        ),
        response_type=TriggerDispatchResponse,
    ):
        response_chunks.append(result)
    
    assert len(response_chunks) == 1
    response = response_chunks[0]
    
    # Should dispatch to 'callback_query_received' event
    assert len(response.events) == 1
    assert response.events[0] == "callback_query_received"


def test_dispatch_invalid_secret_token(plugin_runner):
    """
    Test that an invalid secret token raises a validation error.
    """
    telegram_payload = {
        "update_id": 123456791,
        "message": {
            "message_id": 1,
            "text": "Hello!",
        }
    }
    
    raw_request = build_telegram_webhook_request(
        telegram_payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_token"}
    )
    
    subscription = {
        "endpoint": "https://example.com/webhook",
        "properties": {"secret_token": "correct_token"},  # Require secret token
        "parameters": {},
        "expires_at": -1,
    }
    
    try:
        for result in plugin_runner.invoke(
            access_type=PluginInvokeType.Trigger,
            access_action=TriggerActions.DispatchTriggerEvent,
            payload=TriggerDispatchEventRequest(
                provider="telegram_trigger",
                subscription=subscription,
                credentials={"bot_token": "test_token"},
                credential_type="api-key",
                raw_http_request=raw_request,
                user_id="test_user",
            ),
            response_type=TriggerDispatchResponse,
        ):
            pass
        # Should have raised an error
        assert False, "Expected validation error for invalid secret token"
    except ValueError as e:
        # Expected error
        error_str = str(e)
        assert "secret" in error_str.lower() or "Invalid" in error_str


def test_dispatch_empty_events(plugin_runner):
    """
    Test that unknown payload type returns empty events list.
    """
    # Payload with no known update type
    telegram_payload = {
        "update_id": 123456795,
    }
    
    raw_request = build_telegram_webhook_request(telegram_payload)
    
    subscription = {
        "endpoint": "https://example.com/webhook",
        "properties": {},
        "parameters": {},
        "expires_at": -1,
    }
    
    response_chunks = []
    for result in plugin_runner.invoke(
        access_type=PluginInvokeType.Trigger,
        access_action=TriggerActions.DispatchTriggerEvent,
        payload=TriggerDispatchEventRequest(
            provider="telegram_trigger",
            subscription=subscription,
            credentials={"bot_token": "test_token"},
            credential_type="api-key",
            raw_http_request=raw_request,
            user_id="test_user",
        ),
        response_type=TriggerDispatchResponse,
    ):
        response_chunks.append(result)
    
    assert len(response_chunks) == 1
    response = response_chunks[0]
    
    # Unknown update type should return empty events list
    assert len(response.events) == 0
