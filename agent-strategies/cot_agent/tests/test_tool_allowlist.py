import unittest
from unittest.mock import Mock

from strategies.tool_allowlist import allowed_tool_names, filter_allowed_tools


def _tool(name: str):
    tool = Mock()
    tool.identity.name = name
    return tool


class TestAllowedToolNames(unittest.TestCase):
    def test_none_means_unrestricted(self):
        self.assertIsNone(allowed_tool_names(None))

    def test_empty_list_means_unrestricted(self):
        self.assertIsNone(allowed_tool_names([]))

    def test_empty_string_means_unrestricted(self):
        self.assertIsNone(allowed_tool_names("  "))

    def test_names_are_stripped(self):
        self.assertEqual(
            allowed_tool_names([" lookup ", ""]),
            {"lookup"},
        )

    def test_json_string_is_parsed(self):
        self.assertEqual(
            allowed_tool_names('["lookup"]'),
            {"lookup"},
        )

    def test_plain_string_is_a_single_name(self):
        self.assertEqual(allowed_tool_names("lookup"), {"lookup"})


class TestFilterAllowedTools(unittest.TestCase):
    def setUp(self):
        self.tools = [
            _tool("lookup"),
            _tool("create_ticket"),
        ]

    def test_unrestricted_keeps_all_tools(self):
        self.assertEqual(filter_allowed_tools(self.tools, None), self.tools)
        self.assertEqual(filter_allowed_tools(self.tools, []), self.tools)

    def test_allowlist_keeps_matching_names(self):
        filtered = filter_allowed_tools(self.tools, ["lookup"])
        self.assertEqual([tool.identity.name for tool in filtered], ["lookup"])

    def test_unknown_names_remove_everything(self):
        filtered = filter_allowed_tools(self.tools, ["does_not_exist"])
        self.assertEqual(filtered, [])


if __name__ == "__main__":
    unittest.main()
