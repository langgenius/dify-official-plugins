"""Unit tests for the user_identity_support credential.

The base SDK adds a top-level "user" to the request body whenever the user
argument is truthy. Some OpenAI-compatible gateways reject that optional
parameter, so the credential lets an operator suppress it. Default must keep
today's behaviour: the parameter is still sent.
"""

import unittest
from unittest.mock import patch

from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.interfaces.model.openai_compatible.llm import OAICompatLargeLanguageModel

from models.llm.llm import OpenAILargeLanguageModel


class TestUserIdentitySupport(unittest.TestCase):
    """The credential gates the user argument passed down to the base implementation."""

    def setUp(self):
        # AIModel.__init__ requires model_schemas; pass an empty list to satisfy it.
        self.model = OpenAILargeLanguageModel(model_schemas=[])
        self.base_credentials = {
            "endpoint_url": "https://api.example.com/v1/",
            "api_key": "test-key",
            "mode": "chat",
        }

    def _invoke_with(self, credentials):
        """Invoke and return the user value the base implementation received."""
        with patch.object(OAICompatLargeLanguageModel, "_invoke") as mock_super_invoke:
            self.model._invoke(
                model="test-model",
                credentials=credentials,
                prompt_messages=[UserPromptMessage(content="hi")],
                model_parameters={},
                stream=False,
                user="dify-user-42",
            )
        mock_super_invoke.assert_called_once()
        # _invoke is forwarded positionally: (model, credentials, prompt_messages,
        # model_parameters, tools, stop, stream, user)
        return mock_super_invoke.call_args[0][7]

    def test_user_sent_when_credential_absent(self):
        """Default behaviour is unchanged for existing configurations."""
        self.assertEqual(self._invoke_with(dict(self.base_credentials)), "dify-user-42")

    def test_user_sent_when_credential_supports_it(self):
        """Explicit 'support' keeps the parameter."""
        credentials = dict(self.base_credentials, user_identity_support="support")
        self.assertEqual(self._invoke_with(credentials), "dify-user-42")

    def test_user_omitted_when_credential_disables_it(self):
        """'no_support' drops the parameter, so the SDK never adds it to the body."""
        credentials = dict(self.base_credentials, user_identity_support="no_support")
        self.assertIsNone(self._invoke_with(credentials))


class TestUserIdentitySupportPayload(unittest.TestCase):
    """End-to-end over the SDK's own body construction: the key is absent, not empty."""

    def setUp(self):
        self.model = OpenAILargeLanguageModel(model_schemas=[])
        self.base_credentials = {
            "endpoint_url": "https://api.example.com/v1/",
            "api_key": "test-key",
            "mode": "chat",
        }

    def _captured_body(self, credentials):
        """Invoke for real down to the HTTP call and return the JSON body posted."""
        captured = {}

        def fake_post(url, **kwargs):
            captured.update(kwargs.get("json") or {})
            raise RuntimeError("stop-after-body-built")

        with patch("requests.post", side_effect=fake_post):
            with self.assertRaises(Exception):
                self.model._invoke(
                    model="test-model",
                    credentials=credentials,
                    prompt_messages=[UserPromptMessage(content="hi")],
                    model_parameters={},
                    stream=False,
                    user="dify-user-42",
                )
        return captured

    def test_payload_includes_user_by_default(self):
        body = self._captured_body(dict(self.base_credentials))
        self.assertIn("user", body)
        self.assertEqual(body["user"], "dify-user-42")

    def test_payload_omits_user_when_disabled(self):
        credentials = dict(self.base_credentials, user_identity_support="no_support")
        body = self._captured_body(credentials)
        self.assertNotIn("user", body)


if __name__ == "__main__":
    unittest.main()
