"""
Tests for AzureOpenAILargeLanguageModel._num_tokens_for_tools

Covers an unguarded tool-schema read found by audit:
- `parameters["type"]` was subscripted without a guard, while the `title`,
  `properties` and `required` reads immediately around it were all wrapped in
  `if "<key>" in parameters:`. A tool schema with no top-level `type` therefore
  raised KeyError('type') during token counting.

`PromptMessageTool.parameters` is typed `dict` and is not validated by the SDK, so
arbitrary JSON Schema reaches this method.

This defect is LATENT -- found by audit, with no user report and no field
reproduction. It also sits on the token-counting path rather than the invocation
path, so it is less likely to fire than the equivalent reads in the tongyi and
cohere converters.

No credentials and no network I/O: the method is a pure static function over a
tiktoken encoding.
"""

import sys
import unittest
from pathlib import Path

import tiktoken

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dify_plugin.entities.model.message import PromptMessageTool
from models.llm.llm import AzureOpenAILargeLanguageModel


def _tool(parameters: dict) -> PromptMessageTool:
    return PromptMessageTool(
        name="get_weather",
        description="Look up the weather",
        parameters=parameters,
    )


class NumTokensForToolsTestCase(unittest.TestCase):
    def setUp(self):
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def _count(self, parameters: dict) -> int:
        return AzureOpenAILargeLanguageModel._num_tokens_for_tools(
            self.encoding, [_tool(parameters)]
        )

    def test_schema_without_type_is_counted(self):
        """The audited defect: a schema with no top-level `type` used to raise
        KeyError('type')."""
        tokens = self._count(
            {
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            }
        )

        self.assertGreater(tokens, 0)

    def test_empty_schema_is_counted(self):
        """The degenerate case: every optional key missing at once."""
        self.assertGreater(self._count({}), 0)

    def test_absent_type_does_not_contribute_tokens(self):
        """Dropping the key name along with its value is the point of the guard.

        A schema that differs only by carrying `type` must cost strictly more than one
        that omits it, because the payload really does contain the extra key.
        """
        without_type = self._count({"properties": {}, "required": []})
        with_type = self._count({"type": "object", "properties": {}, "required": []})

        self.assertGreater(with_type, without_type)

    def test_well_formed_schema_count_is_unchanged(self):
        """GUARD RAIL -- passes both before and after the fix by design.

        A fully-specified schema must produce exactly the count it always did, proving
        the guard is inert on the happy path. The expected value is computed from the
        same encoding rather than hard-coded, so it tracks the tokenizer.
        """
        parameters = {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        }
        enc = self.encoding

        expected = 0
        for text in ("type", "function", "name", "get_weather", "description"):
            expected += len(enc.encode(text))
        expected += len(enc.encode("Look up the weather"))
        expected += len(enc.encode("parameters"))
        expected += len(enc.encode("type")) + len(enc.encode("object"))
        expected += len(enc.encode("properties"))
        expected += len(enc.encode("city"))
        expected += len(enc.encode("type")) * 2 + len(enc.encode("string"))
        expected += len(enc.encode("description")) * 2 + len(enc.encode("City name"))
        expected += len(enc.encode("required")) + 3 + len(enc.encode("city"))

        self.assertEqual(self._count(parameters), expected)


if __name__ == "__main__":
    unittest.main()
