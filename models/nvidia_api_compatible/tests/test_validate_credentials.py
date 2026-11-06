"""Unit tests for OpenAILargeLanguageModel.validate_credentials with thinking-mode fallback."""

import unittest
from unittest.mock import MagicMock, patch

from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.openai_compatible.llm import OAICompatLargeLanguageModel

from models.llm.llm import OpenAILargeLanguageModel


class TestValidateCredentials(unittest.TestCase):
    """Tests for validate_credentials override in OpenAILargeLanguageModel."""

    def setUp(self):
        # AIModel.__init__ requires model_schemas; pass an empty list to satisfy it.
        self.model = OpenAILargeLanguageModel(model_schemas=[])
        self.base_credentials = {
            "endpoint_url": "https://api.example.com/v1/",
            "api_key": "test-key",
            "mode": "chat",
        }

    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_successful_validation(self, mock_super_validate):
        """Test that when super().validate_credentials() succeeds, no retry is attempted."""
        mock_super_validate.return_value = None

        # Should not raise
        self.model.validate_credentials("test-model", self.base_credentials)
        mock_super_validate.assert_called_once_with("test-model", self.base_credentials)

    @patch.object(OpenAILargeLanguageModel, "_retry_with_thinking_disabled")
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_thinking_mode_retry_on_budget_tokens_error(self, mock_super_validate, mock_retry):
        """Test that a CredentialsValidateFailedError mentioning budget_tokens triggers thinking retry."""
        mock_super_validate.side_effect = CredentialsValidateFailedError(
            "thinking.enabled,budget_tokens: Input should be >= 1024"
        )
        mock_retry.return_value = None

        # Should not raise — retries and succeeds
        self.model.validate_credentials("claude-opus-4.6", self.base_credentials)

        mock_super_validate.assert_called_once()
        mock_retry.assert_called_once_with("claude-opus-4.6", self.base_credentials)

    @patch.object(OpenAILargeLanguageModel, "_retry_with_thinking_disabled")
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_thinking_mode_retry_on_thinking_keyword(self, mock_super_validate, mock_retry):
        """Test that a CredentialsValidateFailedError mentioning 'thinking' triggers retry."""
        mock_super_validate.side_effect = CredentialsValidateFailedError(
            "thinking parameter is required for this model"
        )
        mock_retry.return_value = None

        self.model.validate_credentials("test-model", self.base_credentials)

        mock_super_validate.assert_called_once()
        mock_retry.assert_called_once()

    @patch.object(OpenAILargeLanguageModel, "_retry_with_thinking_disabled")
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_thinking_retry_also_fails(self, mock_super_validate, mock_retry):
        """Test that when thinking retry also fails, the error is raised."""
        mock_super_validate.side_effect = CredentialsValidateFailedError(
            "budget_tokens: required"
        )
        mock_retry.side_effect = CredentialsValidateFailedError("still failing")

        with self.assertRaises(CredentialsValidateFailedError):
            self.model.validate_credentials("test-model", self.base_credentials)

    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_non_thinking_error_raises_immediately(self, mock_super_validate):
        """Test that an error NOT related to thinking or max_output_tokens raises immediately."""
        mock_super_validate.side_effect = CredentialsValidateFailedError(
            "invalid api key"
        )

        with self.assertRaises(CredentialsValidateFailedError) as ctx:
            self.model.validate_credentials("test-model", self.base_credentials)

        self.assertIn("invalid api key", str(ctx.exception))

    @patch.object(OpenAILargeLanguageModel, "_retry_with_safe_min_tokens")
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_max_output_tokens_retry(self, mock_super_validate, mock_retry):
        """Test that max_output_tokens / integer_below_min_value triggers safe min tokens retry."""
        mock_super_validate.side_effect = CredentialsValidateFailedError(
            "Invalid 'max_output_tokens': integer_below_min_value"
        )
        mock_retry.return_value = None

        self.model.validate_credentials("test-model", self.base_credentials)

        mock_super_validate.assert_called_once()
        mock_retry.assert_called_once_with("test-model", self.base_credentials)

    @patch.object(OpenAILargeLanguageModel, "_retry_with_safe_min_tokens")
    @patch.object(OAICompatLargeLanguageModel, "validate_credentials")
    def test_max_output_tokens_retry_also_fails(self, mock_super_validate, mock_retry):
        """Test that when safe min tokens retry also fails, error is raised."""
        mock_super_validate.side_effect = CredentialsValidateFailedError(
            "Invalid 'max_output_tokens': integer_below_min_value"
        )
        mock_retry.side_effect = CredentialsValidateFailedError("retry failed")

        with self.assertRaises(CredentialsValidateFailedError):
            self.model.validate_credentials("test-model", self.base_credentials)


class TestRetryWithThinkingDisabled(unittest.TestCase):
    """Tests for _retry_with_thinking_disabled method."""

    def setUp(self):
        self.model = OpenAILargeLanguageModel(model_schemas=[])
        self.base_credentials = {
            "endpoint_url": "https://api.example.com/v1/",
            "api_key": "test-key",
            "mode": "chat",
        }

    @patch("models.llm.llm.requests.post")
    def test_retry_sends_thinking_disabled(self, mock_post):
        """Test that the retry request includes thinking: {type: disabled}."""
        resp = MagicMock()
        resp.status_code = 200
        mock_post.return_value = resp

        self.model._retry_with_thinking_disabled("test-model", self.base_credentials)

        mock_post.assert_called_once()
        call_json = mock_post.call_args.kwargs.get("json", {})
        self.assertEqual(call_json.get("thinking"), {"type": "disabled"})

    @patch("models.llm.llm.requests.post")
    def test_retry_uses_chat_completions_endpoint(self, mock_post):
        """Test that chat mode uses chat/completions endpoint."""
        resp = MagicMock()
        resp.status_code = 200
        mock_post.return_value = resp

        self.model._retry_with_thinking_disabled("test-model", self.base_credentials)

        call_url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args[0][0]
        self.assertIn("chat/completions", call_url)

    @patch("models.llm.llm.requests.post")
    def test_retry_completion_mode(self, mock_post):
        """Test retry in completion mode uses completions endpoint."""
        resp = MagicMock()
        resp.status_code = 200
        mock_post.return_value = resp

        credentials = {**self.base_credentials, "mode": "completion"}
        self.model._retry_with_thinking_disabled("test-model", credentials)

        call_json = mock_post.call_args.kwargs.get("json", {})
        self.assertIn("prompt", call_json)
        self.assertNotIn("messages", call_json)

    @patch("models.llm.llm.requests.post")
    def test_retry_failure_raises_error(self, mock_post):
        """Test that a non-200 response during retry raises error."""
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "still failing"
        mock_post.return_value = resp

        with self.assertRaises(CredentialsValidateFailedError):
            self.model._retry_with_thinking_disabled("test-model", self.base_credentials)

    @patch("models.llm.llm.requests.post")
    def test_retry_connection_error(self, mock_post):
        """Test that connection errors during retry are wrapped in CredentialsValidateFailedError."""
        mock_post.side_effect = ConnectionError("Connection refused")

        with self.assertRaises(CredentialsValidateFailedError):
            self.model._retry_with_thinking_disabled("test-model", self.base_credentials)

    @patch("models.llm.llm.requests.post")
    def test_retry_uses_custom_model_name(self, mock_post):
        """Test that endpoint_model_name overrides the model parameter in retry."""
        resp = MagicMock()
        resp.status_code = 200
        mock_post.return_value = resp

        credentials = {**self.base_credentials, "endpoint_model_name": "custom-model"}
        self.model._retry_with_thinking_disabled("original-model", credentials)

        call_json = mock_post.call_args.kwargs.get("json", {})
        self.assertEqual(call_json["model"], "custom-model")

    @patch("models.llm.llm.requests.post")
    def test_retry_normalizes_endpoint_url(self, mock_post):
        """Test that endpoint URLs without trailing slash are normalized."""
        resp = MagicMock()
        resp.status_code = 200
        mock_post.return_value = resp

        credentials = {**self.base_credentials, "endpoint_url": "https://api.example.com/v1"}
        self.model._retry_with_thinking_disabled("test-model", credentials)

        call_url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args[0][0]
        self.assertIn("chat/completions", call_url)


if __name__ == "__main__":
    unittest.main()
