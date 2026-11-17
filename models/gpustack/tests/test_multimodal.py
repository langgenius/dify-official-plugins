"""Exercise the plugin's public SDK entry points with captured HTTP requests."""

# Initialize the SDK's gevent patches before mock imports asyncio/SSL.
# isort: off
from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.text_embedding import (
    MultiModalContent,
    MultiModalContentType,
)
from dify_plugin.errors.model import (
    InvokeBadRequestError,
    InvokeError,
    InvokeAuthorizationError,
)
from models.text_embedding.text_embedding import GPUStackTextEmbeddingModel
from models.rerank.rerank import GPUStackRerankModel

import unittest
from unittest.mock import Mock, patch
from pathlib import Path

import requests
import yaml

# isort: on

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9hQAAAAASUVORK5CYII="


def credentials(**overrides):
    return {
        "endpoint_url": "http://gpustack.test/gateway/v1-openai/",
        "api_key": "test-key",
        "context_size": "32768",
        "vision_support": "support",
        "endpoint_model_name": "deployment-name",
        **overrides,
    }


def content(value, kind=MultiModalContentType.TEXT):
    return MultiModalContent(content=value, content_type=kind)


def response(body):
    result = Mock()
    result.status_code = 200
    result.json.return_value = body
    return result


def embedding(vector):
    return response(
        {"data": [{"index": 0, "embedding": vector}], "usage": {"total_tokens": 5}}
    )


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.model = GPUStackTextEmbeddingModel(model_schemas=[])
        tokenizer = patch.object(
            GPUStackTextEmbeddingModel, "_get_num_tokens_by_gpt2", return_value=1
        )
        tokenizer.start()
        self.addCleanup(tokenizer.stop)

    def test_vision_capability_is_opt_in(self):
        enabled = self.model.get_customizable_model_schema("display", credentials())
        disabled = self.model.get_customizable_model_schema(
            "display", credentials(vision_support="no_support")
        )
        self.assertIn(ModelFeature.VISION, enabled.features or [])
        self.assertNotIn(ModelFeature.VISION, disabled.features or [])

    @patch("requests.post")
    def test_text_and_image_use_same_template_and_preserve_input_order(self, post):
        post.side_effect = [
            embedding([1.0, 0.0]),
            embedding([0.0, 1.0]),
            embedding([0.5, 0.5]),
        ]
        text_result = self.model.invoke(
            "display", credentials(), ["Image: literal text"]
        )
        mixed_result = self.model.invoke_multimodal(
            "display",
            credentials(),
            [content(PNG, MultiModalContentType.IMAGE), content("another text")],
        )
        self.assertEqual(text_result.embeddings, [[1.0, 0.0]])
        self.assertEqual(mixed_result.embeddings, [[0.0, 1.0], [0.5, 0.5]])
        payloads = [call.kwargs["json"] for call in post.call_args_list]
        for call, payload in zip(post.call_args_list, payloads):
            self.assertEqual(call.args[0], "http://gpustack.test/gateway/v1/embeddings")
            self.assertEqual(payload["model"], "deployment-name")
            self.assertNotIn("continue_final_message", payload)
            self.assertNotIn("add_special_tokens", payload)
            self.assertNotIn("add_generation_prompt", payload)
            self.assertEqual(
                [message["role"] for message in payload["messages"]], ["user"]
            )
        self.assertEqual(
            payloads[0]["messages"][0]["content"],
            [{"type": "text", "text": "Image: literal text"}],
        )
        self.assertEqual(
            payloads[1]["messages"][0]["content"][0]["image_url"]["url"],
            "data:image/png;base64," + PNG,
        )
        self.assertEqual(mixed_result.usage.total_tokens, 10)

    @patch("requests.post")
    def test_legacy_text_model_keeps_input_protocol(self, post):
        post.return_value = embedding([1.0, 0.0])
        self.model.invoke(
            "display", credentials(vision_support="no_support"), ["plain text"]
        )
        call = post.call_args
        import json

        payload = call.kwargs.get("json") or json.loads(call.kwargs["data"])
        self.assertEqual(payload["input"], ["plain text"])
        self.assertNotIn("messages", payload)

    @patch("requests.post")
    def test_invalid_image_fails_before_http(self, post):
        with self.assertRaises(InvokeBadRequestError):
            self.model.invoke_multimodal(
                "display",
                credentials(),
                [content("invalid", MultiModalContentType.IMAGE)],
            )
        post.assert_not_called()

    @patch("requests.post")
    def test_embedding_dimensions_must_match(self, post):
        post.side_effect = [embedding([1.0, 0.0]), embedding([1.0, 0.0, 0.0])]
        with self.assertRaises(InvokeError):
            self.model.invoke("display", credentials(), ["one", "two"])

    @patch("requests.post")
    def test_validation_uses_chat_path(self, post):
        post.return_value = embedding([1.0, 0.0])
        self.model.validate_credentials("display", credentials())
        self.assertIn("messages", post.call_args.kwargs["json"])

    @patch("requests.post")
    def test_empty_multimodal_batch_has_zero_usage(self, post):
        result = self.model.invoke_multimodal("display", credentials(), [])
        self.assertEqual(result.embeddings, [])
        self.assertEqual(result.usage.total_tokens, 0)
        post.assert_not_called()

    @patch("requests.post")
    def test_blank_optional_timeout_uses_embedding_default(self, post):
        post.return_value = embedding([1.0, 0.0])
        for timeout in ["", None, "   "]:
            with self.subTest(timeout=timeout):
                self.model.invoke("display", credentials(timeout=timeout), ["q"])
                self.assertEqual(post.call_args.kwargs["timeout"], 600)

    @patch("requests.post")
    def test_null_total_tokens_falls_back_to_prompt_tokens(self, post):
        post.return_value = response(
            {
                "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                "usage": {"total_tokens": None, "prompt_tokens": 7},
            }
        )
        result = self.model.invoke("display", credentials(), ["q"])
        self.assertEqual(result.usage.total_tokens, 7)

    @patch("requests.post")
    def test_existing_data_uri_is_not_double_encoded(self, post):
        post.return_value = embedding([1.0, 0.0])
        uri = "data:image/png;base64," + PNG
        self.model.invoke_multimodal(
            "display", credentials(), [content(uri, MultiModalContentType.IMAGE)]
        )
        part = post.call_args.kwargs["json"]["messages"][0]["content"][0]
        self.assertEqual(part["image_url"]["url"], uri)

    @patch("requests.post")
    def test_optional_template_settings_apply_to_text_and_image(self, post):
        post.side_effect = [embedding([1.0, 0.0]), embedding([0.0, 1.0])]
        config = credentials(
            embedding_system_prompt="Custom retrieval instruction.",
            embedding_chat_template_options='{"continue_final_message":true,"add_special_tokens":true}',
        )
        self.model.invoke("display", config, ["query"])
        self.model.invoke_multimodal(
            "display", config, [content(PNG, MultiModalContentType.IMAGE)]
        )
        for call in post.call_args_list:
            payload = call.kwargs["json"]
            self.assertEqual(
                [message["role"] for message in payload["messages"]],
                ["system", "user", "assistant"],
            )
            self.assertEqual(
                payload["messages"][0]["content"][0]["text"],
                "Custom retrieval instruction.",
            )
            self.assertEqual(
                payload["messages"][-1]["content"], [{"type": "text", "text": ""}]
            )
            self.assertTrue(payload["continue_final_message"])
            self.assertTrue(payload["add_special_tokens"])

    @patch("requests.post")
    def test_model_names_do_not_select_a_template(self, post):
        post.return_value = embedding([1.0, 0.0])
        for name in ["vision-encoder-a", "multimodal-prod-b", "qwen3-vl-embedding"]:
            with self.subTest(name=name):
                self.model.invoke(
                    name, credentials(endpoint_model_name=name), ["query"]
                )
                payload = post.call_args.kwargs["json"]
                self.assertEqual(payload["model"], name)
                self.assertEqual(
                    payload["messages"],
                    [{"role": "user", "content": [{"type": "text", "text": "query"}]}],
                )

    @patch("requests.post")
    def test_invalid_template_options_are_rejected(self, post):
        for options in [
            "not json",
            "[]",
            '{"model":"override"}',
            '{"add_special_tokens":"true"}',
            '{"continue_final_message":true,"add_generation_prompt":true}',
        ]:
            with self.subTest(options=options), self.assertRaises(
                InvokeBadRequestError
            ):
                self.model.invoke(
                    "display",
                    credentials(embedding_chat_template_options=options),
                    ["query"],
                )
        post.assert_not_called()

    @patch("requests.post")
    def test_blank_template_options_use_server_defaults(self, post):
        post.return_value = embedding([1.0, 0.0])
        for options in [None, "", "   ", "{}"]:
            with self.subTest(options=options):
                self.model.invoke(
                    "display",
                    credentials(embedding_chat_template_options=options),
                    ["query"],
                )
                payload = post.call_args.kwargs["json"]
                self.assertNotIn("add_generation_prompt", payload)
                self.assertNotIn("continue_final_message", payload)
                self.assertNotIn("add_special_tokens", payload)

    @patch("requests.post")
    def test_explicit_false_template_option_is_preserved(self, post):
        post.return_value = embedding([1.0, 0.0])
        self.model.invoke(
            "display",
            credentials(
                embedding_chat_template_options='{"add_special_tokens":false,"add_generation_prompt":true}'
            ),
            ["query"],
        )
        payload = post.call_args.kwargs["json"]
        self.assertFalse(payload["add_special_tokens"])
        self.assertTrue(payload["add_generation_prompt"])
        self.assertEqual([message["role"] for message in payload["messages"]], ["user"])

    @patch("requests.post")
    def test_invalid_vectors_are_rejected(self, post):
        for vector in [[], [0.0, 0.0], [float("nan"), 1.0], ["secret", 1.0]]:
            with self.subTest(vector=vector):
                post.return_value = embedding(vector)
                with self.assertRaises(InvokeError):
                    self.model.invoke("display", credentials(), ["text"])

    @patch("requests.post")
    def test_http_authorization_error_is_preserved_and_sanitized(self, post):
        failed = response({})
        failed.status_code = 401
        failed.raise_for_status.side_effect = requests.HTTPError(
            "sensitive URL", response=failed
        )
        post.return_value = failed
        with self.assertRaises(InvokeAuthorizationError) as raised:
            self.model.invoke("display", credentials(), ["text"])
        self.assertNotIn("sensitive", str(raised.exception))
        failed.close.assert_called_once()

    @patch("requests.post")
    def test_multimodal_requires_explicit_vision(self, post):
        with self.assertRaises(InvokeBadRequestError):
            self.model.invoke_multimodal(
                "display",
                credentials(vision_support="no_support"),
                [content(PNG, MultiModalContentType.IMAGE)],
            )
        post.assert_not_called()


class RerankTests(unittest.TestCase):
    def setUp(self):
        self.model = GPUStackRerankModel(model_schemas=[])

    def test_vision_capability(self):
        schema = self.model.get_customizable_model_schema("display", credentials())
        self.assertIn(ModelFeature.VISION, schema.features or [])

    @patch("requests.post")
    def test_visual_rerank_validation_uses_multimodal_contract(self, post):
        post.return_value = response({"results": []})
        self.model.validate_credentials("display", credentials())
        payload = post.call_args.kwargs["json"]
        self.assertTrue(
            all(
                isinstance(doc, dict) and "content" in doc
                for doc in payload["documents"]
            )
        )
        self.assertTrue(
            all(doc["content"][0]["type"] == "text" for doc in payload["documents"])
        )
        self.assertEqual(payload["model"], "deployment-name")

    @patch("requests.post")
    def test_text_rerank_validation_keeps_string_documents(self, post):
        post.return_value = response({"results": []})
        self.model.validate_credentials(
            "display", credentials(vision_support="no_support")
        )
        self.assertTrue(
            all(
                isinstance(doc, str)
                for doc in post.call_args.kwargs["json"]["documents"]
            )
        )

    @patch("requests.post")
    def test_image_query_and_mixed_documents_preserve_indexes(self, post):
        post.return_value = response(
            {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ]
            }
        )
        result = self.model.invoke_multimodal(
            "display",
            credentials(),
            content(PNG, MultiModalContentType.IMAGE),
            [content("text"), content(PNG, MultiModalContentType.IMAGE)],
            top_n=1,
        )
        payload = post.call_args.kwargs["json"]
        self.assertEqual(
            post.call_args.args[0], "http://gpustack.test/gateway/v1/rerank"
        )
        self.assertEqual(payload["model"], "deployment-name")
        image = {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + PNG},
        }
        self.assertEqual(payload["query"], {"content": [image]})
        self.assertEqual(
            payload["documents"],
            [{"content": [{"type": "text", "text": "text"}]}, {"content": [image]}],
        )
        self.assertEqual([doc.index for doc in result.docs], [1])
        self.assertEqual(result.docs[0].text, PNG)

    @patch("requests.post")
    def test_text_query_can_rerank_image(self, post):
        post.return_value = response(
            {"results": [{"index": 0, "relevance_score": 0.8}]}
        )
        self.model.invoke_multimodal(
            "display",
            credentials(),
            content("green square"),
            [content(PNG, MultiModalContentType.IMAGE)],
        )
        self.assertEqual(post.call_args.kwargs["json"]["query"], "green square")

    @patch("requests.post")
    def test_invalid_document_is_rejected_without_index_shift(self, post):
        with self.assertRaises(InvokeBadRequestError):
            self.model.invoke_multimodal(
                "display",
                credentials(),
                content("q"),
                [content("invalid", MultiModalContentType.IMAGE), content("valid")],
            )
        post.assert_not_called()

    @patch("requests.post")
    def test_out_of_range_response_index_is_rejected(self, post):
        post.return_value = response(
            {"results": [{"index": -1, "relevance_score": 0.8}]}
        )
        with self.assertRaises(InvokeError):
            self.model.invoke_multimodal(
                "display", credentials(), content("q"), [content("doc")]
            )

    @patch("requests.post")
    def test_zero_top_n_returns_empty_without_http(self, post):
        result = self.model.invoke_multimodal(
            "display", credentials(), content("q"), [content("doc")], top_n=0
        )
        self.assertEqual(result.docs, [])
        post.assert_not_called()

    @patch("requests.post")
    def test_legacy_text_default_and_endpoint_alias(self, post):
        post.return_value = response(
            {
                "results": [
                    {
                        "index": 0,
                        "relevance_score": 0.8,
                        "document": {"text": "returned text"},
                    }
                ]
            }
        )
        result = self.model.invoke(
            "display", credentials(vision_support="no_support"), "q", ["doc"]
        )
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["top_n"], 3)
        self.assertEqual(payload["model"], "deployment-name")
        self.assertEqual(payload["documents"], ["doc"])
        self.assertEqual(post.call_args.kwargs["timeout"], 10)
        self.assertEqual(result.docs[0].text, "returned text")

    @patch("requests.post")
    def test_blank_optional_timeout_uses_rerank_default(self, post):
        post.return_value = response({"results": []})
        for timeout in ["", None, "   "]:
            with self.subTest(timeout=timeout):
                self.model.invoke("display", credentials(timeout=timeout), "q", ["doc"])
                self.assertEqual(post.call_args.kwargs["timeout"], 10)

    @patch("requests.post")
    def test_threshold_and_sorting(self, post):
        post.return_value = response(
            {
                "results": [
                    {"index": 0, "relevance_score": 0.2},
                    {"index": 1, "relevance_score": 0.8},
                ]
            }
        )
        result = self.model.invoke_multimodal(
            "display",
            credentials(),
            content("q"),
            [content("one"), content("two")],
            score_threshold=0.5,
        )
        self.assertEqual([doc.index for doc in result.docs], [1])

    @patch("requests.post")
    def test_invalid_indexes_and_scores(self, post):
        cases = [
            [{"index": 2, "relevance_score": 0.8}],
            [{"index": 0, "relevance_score": float("nan")}],
            [
                {"index": 0, "relevance_score": 0.8},
                {"index": 0, "relevance_score": 0.7},
            ],
        ]
        for items in cases:
            with self.subTest(items=items):
                post.return_value = response({"results": items})
                with self.assertRaises(InvokeError):
                    self.model.invoke_multimodal(
                        "display", credentials(), content("q"), [content("doc")]
                    )

    @patch("requests.post")
    def test_empty_docs_skip_http(self, post):
        self.assertEqual(self.model.invoke("display", credentials(), "q", []).docs, [])
        self.assertEqual(
            self.model.invoke_multimodal(
                "display", credentials(), content("q"), []
            ).docs,
            [],
        )
        post.assert_not_called()


class ConfigurationTests(unittest.TestCase):
    def test_duplicate_vision_fields_have_consistent_rendered_labels(self):
        # Dify BaseForm selects the first schema when rendering the same field name.
        path = Path(__file__).resolve().parents[1] / "provider/gpustack.yaml"
        forms = yaml.safe_load(path.read_text(encoding="utf-8"))[
            "model_credential_schema"
        ]["credential_form_schemas"]
        vision_forms = [form for form in forms if form["variable"] == "vision_support"]
        for form in vision_forms[1:]:
            self.assertEqual(form["label"], vision_forms[0]["label"])
            self.assertEqual(form["options"], vision_forms[0]["options"])

    def test_template_guidance_survives_sdk_schema_serialization(self):
        from dify_plugin.entities.model.provider import ModelProviderConfiguration

        path = Path(__file__).resolve().parents[1] / "provider/gpustack.yaml"
        config = ModelProviderConfiguration(
            **yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        forms = {
            form.variable: form
            for form in config.model_credential_schema.credential_form_schemas
        }
        for variable in ["embedding_system_prompt", "embedding_chat_template_options"]:
            form = forms[variable]
            self.assertIsNotNone(form.placeholder)
            self.assertTrue(form.model_dump(mode="json", by_alias=True)["placeholder"])
        self.assertIn(
            "continue_final_message",
            forms["embedding_chat_template_options"].placeholder.en_us,
        )
        self.assertEqual(forms["embedding_chat_template_options"].default, "")

    def test_template_controls_only_apply_to_visual_embeddings(self):
        path = Path(__file__).resolve().parents[1] / "provider/gpustack.yaml"
        forms = yaml.safe_load(path.read_text(encoding="utf-8"))[
            "model_credential_schema"
        ]["credential_form_schemas"]
        for variable in ["embedding_system_prompt", "embedding_chat_template_options"]:
            form = next(item for item in forms if item["variable"] == variable)
            for model_type, vision, expected in [
                ("text-embedding", "support", True),
                ("text-embedding", "no_support", False),
                ("rerank", "support", False),
                ("llm", "support", False),
            ]:
                values = {"__model_type": model_type, "vision_support": vision}
                self.assertEqual(
                    all(
                        values.get(rule["variable"]) == rule["value"]
                        for rule in form["show_on"]
                    ),
                    expected,
                )

    def test_vision_option_visible_for_both_model_types(self):
        path = Path(__file__).resolve().parents[1] / "provider/gpustack.yaml"
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        forms = config["model_credential_schema"]["credential_form_schemas"]
        # Dify combines show_on conditions with AND, not OR.
        for model_type in ["llm", "text-embedding", "rerank"]:
            for variable in ["vision_support", "endpoint_model_name"]:
                visible = [
                    form
                    for form in forms
                    if form["variable"] == variable
                    and all(
                        rule["variable"] == "__model_type"
                        and rule["value"] == model_type
                        for rule in form.get("show_on", [])
                    )
                ]
                self.assertEqual(len(visible), 1, (model_type, variable))

    def test_gpu_stack_url_variants(self):
        from models.multimodal import api_base_url

        for suffix in ["", "/", "/v1", "/v1/", "/v1-openai", "/v1-openai/"]:
            self.assertEqual(
                api_base_url(
                    credentials(endpoint_url="http://gpu.test/proxy" + suffix)
                ),
                "http://gpu.test/proxy/v1",
            )


if __name__ == "__main__":
    unittest.main()
