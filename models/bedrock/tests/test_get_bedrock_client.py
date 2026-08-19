"""Unit tests for provider.get_bedrock_client.

Covers the three authentication paths and the IAM-Role freshness fix from
issue #3519 (ExpiredTokenException when using SSO/SAML temporary
credentials with `saml2aws login` / `aws sso login`).
"""

import importlib.util
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dify_plugin.errors.model import InvokeBadRequestError

_CLIENT_PATH = (
    Path(__file__).resolve().parent.parent / "provider" / "get_bedrock_client.py"
)
_spec = importlib.util.spec_from_file_location("get_bedrock_client", _CLIENT_PATH)
get_bedrock_client = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(get_bedrock_client)


_BASE_CREDENTIALS = {
    "aws_region": "us-east-1",
}


def _client_mock(*, session_calls: list | None = None) -> MagicMock:
    """Return a MagicMock boto3.client with optional session call tracking."""
    return MagicMock(name="boto3.client")


class TestRegionAndEndpointValidation:
    def test_missing_aws_region_raises(self) -> None:
        with pytest.raises(InvokeBadRequestError, match="aws_region is required"):
            get_bedrock_client.get_bedrock_client("bedrock-runtime", {})

    def test_both_endpoint_and_proxy_raises(self) -> None:
        creds = {
            **_BASE_CREDENTIALS,
            "bedrock_endpoint_url": "https://example.com",
            "bedrock_proxy_url": "proxy.example.com:8080",
        }
        with pytest.raises(InvokeBadRequestError, match="Cannot use both"):
            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)


class TestApiKeyMode:
    def setup_method(self) -> None:
        # Make sure no leftover bearer token from a prior test leaks in.
        os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)

    def teardown_method(self) -> None:
        os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)

    def test_missing_bedrock_api_key_raises(self) -> None:
        creds = {**_BASE_CREDENTIALS, "auth_method": "API_Key"}
        with pytest.raises(InvokeBadRequestError, match="bedrock_api_key is required"):
            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)

    def test_api_key_sets_bearer_token_env(self) -> None:
        creds = {
            **_BASE_CREDENTIALS,
            "auth_method": "API_Key",
            "bedrock_api_key": "sk-test-1234",
        }
        with patch.object(
            get_bedrock_client.boto3, "client", return_value=MagicMock()
        ) as mock_client:
            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)
        assert os.environ["AWS_BEARER_TOKEN_BEDROCK"] == "sk-test-1234"
        mock_client.assert_called_once()


class TestAccessSecretKeyMode:
    def test_explicit_keys_passed_to_client(self) -> None:
        creds = {
            **_BASE_CREDENTIALS,
            "auth_method": "Access_Secret_Key",
            "aws_access_key_id": "AKIA-TEST",
            "aws_secret_access_key": "secret-test",
        }
        with patch.object(
            get_bedrock_client.boto3, "client", return_value=MagicMock()
        ) as mock_client:
            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)
        kwargs = mock_client.call_args.kwargs
        assert kwargs["aws_access_key_id"] == "AKIA-TEST"
        assert kwargs["aws_secret_access_key"] == "secret-test"

    def test_default_auth_method_is_access_secret_key(self) -> None:
        # When auth_method is missing, default to Access_Secret_Key.
        creds = {
            **_BASE_CREDENTIALS,
            "aws_access_key_id": "AKIA-DEFAULT",
            "aws_secret_access_key": "secret-default",
        }
        with patch.object(
            get_bedrock_client.boto3, "client", return_value=MagicMock()
        ) as mock_client:
            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)
        kwargs = mock_client.call_args.kwargs
        assert kwargs["aws_access_key_id"] == "AKIA-DEFAULT"


class TestIamRoleMode:
    """IAM-Role mode relies on the default credential chain (saml2aws,
    aws sso, IMDS, etc.). The fix from issue #3519 ensures each call
    builds the client from a fresh boto3.Session so disk-refreshed
    credentials are picked up on every invocation.
    """

    def setup_method(self) -> None:
        os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)

    def teardown_method(self) -> None:
        os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)

    def test_iam_role_uses_fresh_boto3_session(self) -> None:
        creds = {**_BASE_CREDENTIALS, "auth_method": "IAM_Role"}

        with (
            patch.object(
                get_bedrock_client.boto3, "Session", return_value=MagicMock()
            ) as mock_session_cls,
            patch.object(
                MagicMock(), "client", return_value=MagicMock()
            ) as mock_session_client,
        ):
            mock_session = mock_session_cls.return_value
            mock_session.client = mock_session_client

            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)

        # Each IAM-Role call must construct a fresh Session so disk-
        # refreshed credentials are picked up.
        mock_session_cls.assert_called_once_with()
        mock_session_client.assert_called_once()

    def test_iam_role_does_not_use_default_boto3_client(self) -> None:
        # The default `boto3.client(...)` path uses the default session
        # and caches credentials in-process — the bug from #3519. After
        # the fix, the IAM-Role branch must NOT go through that path.
        creds = {**_BASE_CREDENTIALS, "auth_method": "IAM_Role"}

        with (
            patch.object(
                get_bedrock_client.boto3, "client", return_value=MagicMock()
            ) as mock_default_client,
            patch.object(
                get_bedrock_client.boto3, "Session", return_value=MagicMock()
            ) as mock_session_cls,
        ):
            mock_session = mock_session_cls.return_value
            mock_session.client = MagicMock(return_value=MagicMock())

            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)

        mock_default_client.assert_not_called()
        mock_session_cls.assert_called_once()

    def test_iam_role_pops_stale_bearer_token(self) -> None:
        # If a previous API_Key auth set AWS_BEARER_TOKEN_BEDROCK, the
        # IAM-Role branch must clear it so boto3's default chain is used.
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = "stale-key"
        creds = {**_BASE_CREDENTIALS, "auth_method": "IAM_Role"}

        with patch.object(
            get_bedrock_client.boto3, "Session", return_value=MagicMock()
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.client = MagicMock(return_value=MagicMock())

            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)

        assert "AWS_BEARER_TOKEN_BEDROCK" not in os.environ

    def test_two_consecutive_iam_role_calls_make_two_sessions(self) -> None:
        # The whole point of the fix: a second call after the user
        # refreshes credentials externally must build a second Session
        # (so it re-reads the credentials file).
        creds = {**_BASE_CREDENTIALS, "auth_method": "IAM_Role"}

        with patch.object(
            get_bedrock_client.boto3, "Session", return_value=MagicMock()
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.client = MagicMock(return_value=MagicMock())

            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)
            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)

        assert mock_session_cls.call_count == 2


class TestEndpointUrl:
    def test_endpoint_url_only_applies_to_bedrock_runtime(self) -> None:
        creds = {
            **_BASE_CREDENTIALS,
            "auth_method": "Access_Secret_Key",
            "aws_access_key_id": "AKIA",
            "aws_secret_access_key": "secret",
            "bedrock_endpoint_url": "https://vpce.example.com",
        }
        with patch.object(
            get_bedrock_client.boto3, "client", return_value=MagicMock()
        ) as mock_client:
            get_bedrock_client.get_bedrock_client("bedrock", creds)
        # Non-runtime service should NOT receive the endpoint URL.
        assert "endpoint_url" not in mock_client.call_args.kwargs

    def test_endpoint_url_applied_to_bedrock_runtime(self) -> None:
        creds = {
            **_BASE_CREDENTIALS,
            "auth_method": "Access_Secret_Key",
            "aws_access_key_id": "AKIA",
            "aws_secret_access_key": "secret",
            "bedrock_endpoint_url": "https://vpce.example.com",
        }
        with patch.object(
            get_bedrock_client.boto3, "client", return_value=MagicMock()
        ) as mock_client:
            get_bedrock_client.get_bedrock_client("bedrock-runtime", creds)
        assert (
            mock_client.call_args.kwargs["endpoint_url"] == "https://vpce.example.com"
        )
