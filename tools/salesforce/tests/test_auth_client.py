import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider.client import create_client

OAUTH = {"auth_method": "client_credentials", "consumer_key": "client-id", "consumer_secret": "secret", "domain": "organization.my"}

@pytest.mark.parametrize("domain", ["organization.my", "organization--sandbox.sandbox.my"])
def test_oauth_sdk_arguments(domain):
    with patch("provider.client.Salesforce") as sf:
        create_client({**OAUTH, "domain": domain})
    sf.assert_called_once_with(consumer_key="client-id", consumer_secret="secret", domain=domain)

def test_default_legacy_arguments():
    with patch("provider.client.Salesforce") as sf:
        create_client({"username": "user", "password": "pass", "security_token": "token", "domain": "test"})
    sf.assert_called_once_with(username="user", password="pass", security_token="token", domain="test")

@pytest.mark.parametrize("domain", ["", "login", "test", "https://organization.my.salesforce.com", "organization.my.salesforce.com"])
def test_invalid_oauth_domains(domain):
    with pytest.raises(ValueError, match="My Domain"):
        create_client({**OAUTH, "domain": domain})

@pytest.mark.parametrize("field", ["consumer_key", "consumer_secret"])
def test_oauth_missing_credentials(field):
    with pytest.raises(ValueError, match="client"):
        create_client({**OAUTH, field: ""})

def test_unknown_method():
    with pytest.raises(ValueError, match="Unsupported"):
        create_client({"auth_method": "unknown"})

def test_provider_validation_uses_oauth():
    from provider.salesforce import SalesforceProvider
    provider = object.__new__(SalesforceProvider)
    with patch("provider.client.Salesforce") as sf:
        provider._validate_credentials(OAUTH)
    sf.return_value.query.assert_called_once()
    assert sf.call_args.kwargs == {"consumer_key": "client-id", "consumer_secret": "secret", "domain": "organization.my"}

@pytest.mark.parametrize("kind", ["case", "message"])
def test_tool_entrypoints_use_oauth(kind):
    from tools.create_case import CreateCaseTool
    from tools.send_message import SendMessageTool
    cls = CreateCaseTool if kind == "case" else SendMessageTool
    tool = object.__new__(cls); tool.runtime = SimpleNamespace(credentials=OAUTH)
    tool.create_text_message = lambda text: {"text": text}
    tool.create_json_message = lambda obj: {"json": obj}
    sf = MagicMock();sf.Case.create.return_value={"success": True, "id": "case-id"};sf.FeedItem.create.return_value={"success": True,"id":"feed-id"};sf.restful.return_value={"id":"user-id"}
    with patch("provider.client.Salesforce", return_value=sf):
        result=list(tool._invoke({"subject":"subject", "description":"description"} if kind=="case" else {"message_text":"hello"}))
    assert any("json" in m for m in result)
    if kind=="case": sf.Case.create.assert_called_once()
    else:
        sf.query.assert_not_called();sf.restful.assert_called_once_with("chatter/users/me")
        assert sf.FeedItem.create.call_args.args[0]["ParentId"]=="user-id"

def test_real_sdk_uses_oauth_token_post():
    response=MagicMock();response.status_code=200;response.json.return_value={"access_token":"token", "instance_url":"https://organization.my.salesforce.com"}
    with patch("requests.sessions.Session.request",return_value=response) as request:
        create_client(OAUTH)
    args=request.call_args
    assert args.kwargs.get("method", args.args[0] if args.args else None)=="POST"
    assert args.kwargs.get("url", args.args[1] if len(args.args)>1 else None)=="https://organization.my.salesforce.com/services/oauth2/token"
    assert args.kwargs["data"]["grant_type"]=="client_credentials"
