"""Unit tests for OpenAILargeLanguageModel.remote_models.

Mirrors the shape of the first-party ``models/openai`` plugin's
``remote_models`` but, because this plugin has no predefined catalog,
every model the endpoint advertises is returned. The user picks
which one to add.

The OpenAI SDK's ``models.list()`` returns a paginated iterator
of objects with an ``.id`` attribute. We mock the SDK at the
module-import boundary so the unit test does not require network
access.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from models.llm.llm import OpenAILargeLanguageModel


class _RemoteModel:
    def __init__(self, model_id: str) -> None:
        self.id = model_id


class TestRemoteModels(unittest.TestCase):
    """``remote_models`` discovers every model the configured endpoint advertises."""

    def setUp(self) -> None:
        self.model = OpenAILargeLanguageModel(model_schemas=[])
        self.base_credentials = {
            "endpoint_url": "https://api.example.com/v1/",
            "api_key": "test-key",
            "mode": "chat",
            "context_size": "4096",
        }

    def test_remote_models_uses_openai_sdk_models_list(self) -> None:
        """The discovery call must go through the OpenAI SDK, not raw HTTP."""
        fake_client = MagicMock()
        fake_client.models.list.return_value = iter(
            [_RemoteModel("gpt-4o-mini"), _RemoteModel("custom-finetune-1")]
        )

        with patch("models.llm.llm.OpenAI", return_value=fake_client) as openai_cls:
            result = self.model.remote_models(self.base_credentials)

        openai_cls.assert_called_once_with(
            api_key="test-key",
            base_url="https://api.example.com/v1/",
            default_headers={},
        )
        fake_client.models.list.assert_called_once_with()
        self.assertEqual(
            [entity.model for entity in result], ["gpt-4o-mini", "custom-finetune-1"]
        )

    def test_remote_models_returns_one_entity_per_id(self) -> None:
        """Each discovered model ID becomes one ``AIModelEntity``."""
        fake_client = MagicMock()
        fake_client.models.list.return_value = iter(
            [_RemoteModel("a"), _RemoteModel("b"), _RemoteModel("c")]
        )

        with patch("models.llm.llm.OpenAI", return_value=fake_client):
            result = self.model.remote_models(self.base_credentials)

        self.assertEqual(len(result), 3)
        # The model IDs are preserved verbatim on the returned entities.
        self.assertEqual([entity.model for entity in result], ["a", "b", "c"])

    def test_remote_models_skips_entries_without_id(self) -> None:
        """An SDK response without ``.id`` (e.g. an empty stub) is dropped."""
        fake_client = MagicMock()
        fake_client.models.list.return_value = iter(
            [_RemoteModel("a"), SimpleNamespace(id=None), _RemoteModel("b")]
        )

        with patch("models.llm.llm.OpenAI", return_value=fake_client):
            result = self.model.remote_models(self.base_credentials)

        self.assertEqual([entity.model for entity in result], ["a", "b"])

    def test_remote_models_returns_empty_when_endpoint_url_missing(self) -> None:
        """Missing endpoint_url short-circuits to an empty list, not an exception."""
        creds = dict(self.base_credentials)
        creds.pop("endpoint_url")
        self.assertEqual(self.model.remote_models(creds), [])

    def test_remote_models_returns_empty_on_sdk_failure(self) -> None:
        """Discovery is best-effort: a transport or auth failure yields []."""
        with patch(
            "models.llm.llm.OpenAI", side_effect=RuntimeError("connection refused")
        ):
            self.assertEqual(self.model.remote_models(self.base_credentials), [])

    def test_remote_models_passes_extra_headers(self) -> None:
        """``extra_headers`` from the credential reach the OpenAI client constructor."""
        creds = dict(self.base_credentials)
        creds["extra_headers"] = {"X-Custom": "value"}

        fake_client = MagicMock()
        fake_client.models.list.return_value = iter([_RemoteModel("a")])

        with patch("models.llm.llm.OpenAI", return_value=fake_client) as openai_cls:
            self.model.remote_models(creds)

        openai_cls.assert_called_once_with(
            api_key="test-key",
            base_url="https://api.example.com/v1/",
            default_headers={"X-Custom": "value"},
        )

    def test_remote_models_entity_uses_plugin_customizations(self) -> None:
        """Each returned entity flows through ``get_customizable_model_schema``.

        The plugin augments the parent class's default schema with
        ``response_format`` and ``agent_thought`` support. The returned
        entity must carry the augmentation, which proves the discovery
        path runs through the same schema builder the user gets when
        adding a model manually.
        """
        creds = dict(self.base_credentials)
        creds["structured_output_support"] = "supported"
        creds["agent_thought_support"] = "supported"

        fake_client = MagicMock()
        fake_client.models.list.return_value = iter([_RemoteModel("gpt-4o-mini")])

        with patch("models.llm.llm.OpenAI", return_value=fake_client):
            result = self.model.remote_models(creds)

        # Confirm the schema came from the plugin's own builder.
        self.assertEqual(result[0].model, "gpt-4o-mini")
        rule_names = {rule.name for rule in result[0].parameter_rules}
        self.assertIn("response_format", rule_names)
        self.assertIn("enable_thinking", rule_names)
