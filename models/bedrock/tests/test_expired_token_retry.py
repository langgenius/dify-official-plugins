"""Unit tests for expired AWS token detection, client caching, and retry logic."""
import pytest
from unittest.mock import patch, MagicMock

from provider.get_bedrock_client import (
    is_expired_token_error,
    get_bedrock_client,
    invalidate_client_cache,
    _client_cache,
)


class TestIsExpiredTokenError:
    """Tests for the is_expired_token_error helper."""

    def test_detects_expired_token_exception(self):
        exc = Exception(
            "An error occurred (ExpiredTokenException) when calling the "
            "GetInferenceProfile operation: The security token included in "
            "the request is expired"
        )
        assert is_expired_token_error(exc) is True

    def test_detects_expired_keyword(self):
        exc = Exception("Token has expired")
        assert is_expired_token_error(exc) is True

    def test_detects_security_token_keyword(self):
        exc = Exception("The security token is invalid")
        assert is_expired_token_error(exc) is True

    def test_does_not_match_unrelated_error(self):
        exc = Exception("Model not found: us.anthropic.claude-opus-4-8")
        assert is_expired_token_error(exc) is False

    def test_does_not_match_access_denied(self):
        exc = Exception("AccessDeniedException: User is not authorized")
        assert is_expired_token_error(exc) is False

    def test_does_not_match_throttling(self):
        exc = Exception("ThrottlingException: Rate exceeded")
        assert is_expired_token_error(exc) is False

    def test_case_insensitive(self):
        exc = Exception("EXPIREDTOKENEXCEPTION: token expired")
        assert is_expired_token_error(exc) is True


class TestClientCaching:
    """Tests for boto3 client caching and invalidation."""

    def setup_method(self):
        """Clear cache before each test."""
        _client_cache.clear()

    @patch("provider.get_bedrock_client.boto3")
    def test_same_credentials_returns_cached_client(self, mock_boto3):
        """Repeated calls with same credentials should return the same client."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_boto3.Session.return_value = MagicMock(
            get_credentials=MagicMock(return_value=None)
        )

        credentials = {
            "aws_region": "us-east-1",
            "auth_method": "IAM_Role",
        }

        client1 = get_bedrock_client("bedrock-runtime", credentials)
        client2 = get_bedrock_client("bedrock-runtime", credentials)

        assert client1 is client2
        # boto3.client should only be called once (cached on second call)
        assert mock_boto3.client.call_count == 1

    @patch("provider.get_bedrock_client.boto3")
    def test_different_service_creates_separate_clients(self, mock_boto3):
        """Different service names should get different cached clients."""
        mock_boto3.client.side_effect = [MagicMock(), MagicMock()]
        mock_boto3.Session.return_value = MagicMock(
            get_credentials=MagicMock(return_value=None)
        )

        credentials = {
            "aws_region": "us-east-1",
            "auth_method": "IAM_Role",
        }

        client1 = get_bedrock_client("bedrock-runtime", credentials)
        client2 = get_bedrock_client("bedrock", credentials)

        assert client1 is not client2
        assert mock_boto3.client.call_count == 2

    @patch("provider.get_bedrock_client.boto3")
    def test_invalidate_clears_cache(self, mock_boto3):
        """After invalidation, next call creates a fresh client."""
        mock_boto3.client.side_effect = [MagicMock(name="old"), MagicMock(name="new")]
        mock_boto3.Session.return_value = MagicMock(
            get_credentials=MagicMock(return_value=None)
        )

        credentials = {
            "aws_region": "us-east-1",
            "auth_method": "IAM_Role",
        }

        client1 = get_bedrock_client("bedrock-runtime", credentials)
        invalidate_client_cache()
        client2 = get_bedrock_client("bedrock-runtime", credentials)

        assert client1 is not client2
        assert mock_boto3.client.call_count == 2


class TestGetBedrockClientIAMRole:
    """Tests for IAM Role credential refresh in get_bedrock_client."""

    def setup_method(self):
        _client_cache.clear()

    @patch("provider.get_bedrock_client.boto3")
    def test_iam_role_creates_fresh_session(self, mock_boto3):
        """IAM Role mode should create a fresh boto3.Session to read latest creds."""
        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_frozen = MagicMock()
        mock_frozen.access_key = "ASIAFRESHKEY"
        mock_frozen.secret_key = "freshsecret"
        mock_frozen.token = "freshtoken123"
        mock_creds.get_frozen_credentials.return_value = mock_frozen
        mock_session.get_credentials.return_value = mock_creds
        mock_boto3.Session.return_value = mock_session
        mock_boto3.client.return_value = MagicMock()

        credentials = {
            "aws_region": "us-east-1",
            "auth_method": "IAM_Role",
        }

        get_bedrock_client("bedrock-runtime", credentials)

        # Verify a fresh session was created
        mock_boto3.Session.assert_called_once()
        # Verify the frozen credentials were passed to the client
        mock_boto3.client.assert_called_once()
        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "ASIAFRESHKEY"
        assert call_kwargs["aws_secret_access_key"] == "freshsecret"
        assert call_kwargs["aws_session_token"] == "freshtoken123"

    @patch("provider.get_bedrock_client.boto3")
    def test_iam_role_no_session_token_when_long_lived(self, mock_boto3):
        """Long-lived IAM creds (no token) should not set session token."""
        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_frozen = MagicMock()
        mock_frozen.access_key = "AKIALONGLIVEDKEY"
        mock_frozen.secret_key = "longlivedsecret"
        mock_frozen.token = None
        mock_creds.get_frozen_credentials.return_value = mock_frozen
        mock_session.get_credentials.return_value = mock_creds
        mock_boto3.Session.return_value = mock_session
        mock_boto3.client.return_value = MagicMock()

        credentials = {
            "aws_region": "us-east-1",
            "auth_method": "IAM_Role",
        }

        get_bedrock_client("bedrock-runtime", credentials)

        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "AKIALONGLIVEDKEY"
        assert "aws_session_token" not in call_kwargs


class TestGetBedrockClientAccessSecretKey:
    """Tests for Access_Secret_Key mode with optional session token."""

    def setup_method(self):
        _client_cache.clear()

    @patch("provider.get_bedrock_client.boto3")
    def test_passes_session_token_when_provided(self, mock_boto3):
        mock_boto3.client.return_value = MagicMock()

        credentials = {
            "aws_region": "us-east-1",
            "auth_method": "Access_Secret_Key",
            "aws_access_key_id": "ASIATEMPKEY",
            "aws_secret_access_key": "tempsecret",
            "aws_session_token": "temptoken456",
        }

        get_bedrock_client("bedrock-runtime", credentials)

        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "ASIATEMPKEY"
        assert call_kwargs["aws_secret_access_key"] == "tempsecret"
        assert call_kwargs["aws_session_token"] == "temptoken456"

    @patch("provider.get_bedrock_client.boto3")
    def test_no_session_token_when_not_provided(self, mock_boto3):
        mock_boto3.client.return_value = MagicMock()

        credentials = {
            "aws_region": "us-east-1",
            "auth_method": "Access_Secret_Key",
            "aws_access_key_id": "AKIAREGULARKEY",
            "aws_secret_access_key": "regularsecret",
        }

        get_bedrock_client("bedrock-runtime", credentials)

        call_kwargs = mock_boto3.client.call_args[1]
        assert call_kwargs["aws_access_key_id"] == "AKIAREGULARKEY"
        assert call_kwargs["aws_secret_access_key"] == "regularsecret"
        assert "aws_session_token" not in call_kwargs


class TestInvokeRetryOnExpiredToken:
    """Tests for the _invoke retry-on-expired logic in the LLM class."""

    def setup_method(self):
        _client_cache.clear()

    def _create_model_instance(self):
        """Create a BedrockLargeLanguageModel with mocked parent __init__."""
        from models.llm.llm import BedrockLargeLanguageModel

        with patch("dify_plugin.LargeLanguageModel.__init__", return_value=None):
            model = BedrockLargeLanguageModel.__new__(BedrockLargeLanguageModel)
        return model

    @patch("provider.get_bedrock_client.boto3")
    def test_retry_calls_invoke_inner_twice_on_expired(self, mock_boto3):
        """When first call fails with expired token, retry should succeed."""
        model = self._create_model_instance()

        call_count = {"n": 0}
        expected_result = MagicMock()

        def mock_invoke_inner(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception(
                    "ExpiredTokenException: The security token included in the request is expired"
                )
            return expected_result

        with patch.object(model, "_invoke_inner", side_effect=mock_invoke_inner):
            result = model._invoke(
                model="test-model",
                credentials={"aws_region": "us-east-1", "auth_method": "IAM_Role"},
                prompt_messages=[],
                model_parameters={},
            )

        assert result == expected_result
        assert call_count["n"] == 2

    @patch("provider.get_bedrock_client.boto3")
    def test_retry_invalidates_client_cache(self, mock_boto3):
        """On expired token, the client cache should be invalidated before retry."""
        model = self._create_model_instance()

        # Pre-populate cache
        _client_cache["some_key"] = MagicMock()

        def mock_invoke_inner(*args, **kwargs):
            raise Exception(
                "ExpiredTokenException: The security token included in the request is expired"
            )

        with patch.object(model, "_invoke_inner", side_effect=mock_invoke_inner):
            with pytest.raises(Exception):
                model._invoke(
                    model="test-model",
                    credentials={"aws_region": "us-east-1", "auth_method": "IAM_Role"},
                    prompt_messages=[],
                    model_parameters={},
                )

        # Cache should have been cleared
        assert len(_client_cache) == 0

    @patch("provider.get_bedrock_client.boto3")
    def test_raises_auth_error_when_both_attempts_fail(self, mock_boto3):
        """When both attempts fail with expired token, raise clear auth error."""
        from dify_plugin.errors.model import InvokeAuthorizationError

        model = self._create_model_instance()

        def mock_invoke_inner(*args, **kwargs):
            raise Exception(
                "ExpiredTokenException: The security token included in the request is expired"
            )

        with patch.object(model, "_invoke_inner", side_effect=mock_invoke_inner):
            with pytest.raises(InvokeAuthorizationError, match="re-authenticate"):
                model._invoke(
                    model="test-model",
                    credentials={"aws_region": "us-east-1", "auth_method": "IAM_Role"},
                    prompt_messages=[],
                    model_parameters={},
                )

    @patch("provider.get_bedrock_client.boto3")
    def test_non_expired_errors_propagate_immediately(self, mock_boto3):
        """Non-expired errors should not trigger retry."""
        model = self._create_model_instance()

        call_count = {"n": 0}

        def mock_invoke_inner(*args, **kwargs):
            call_count["n"] += 1
            raise Exception("ModelNotFoundException: Model not found")

        with patch.object(model, "_invoke_inner", side_effect=mock_invoke_inner):
            with pytest.raises(Exception, match="Model not found"):
                model._invoke(
                    model="test-model",
                    credentials={"aws_region": "us-east-1", "auth_method": "IAM_Role"},
                    prompt_messages=[],
                    model_parameters={},
                )

        # Should only be called once — no retry for non-expired errors
        assert call_count["n"] == 1
