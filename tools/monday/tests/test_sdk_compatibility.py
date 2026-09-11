import json
import unittest
from unittest.mock import patch

from requests import Response

from src.monday import MondayCredential, MondayPlugin


class MondayCompatibilityTest(unittest.TestCase):
    def test_sdk_operations_preserve_api_results(self):
        plugin = MondayPlugin(credentials=MondayCredential(token="test-key"))
        board = {
            "id": "10",
            "name": "Work",
            "groups": [{"id": "topics"}],
            "columns": [{"id": "status"}],
        }
        cases = [
            ("fetch_boards", {}, {"boards": [board]}, "boards", "10"),
            ("fetch_board_by_id", {"board_id": "10"}, {"boards": [board]}, "boards", "10"),
            (
                "fetch_groups_by_board_id",
                {"board_id": "10"},
                {"boards": [board]},
                "groups",
                "topics",
            ),
            (
                "fetch_columns_by_board_id",
                {"board_id": "10"},
                {"boards": [board]},
                "columns",
                "status",
            ),
            (
                "create_item",
                {
                    "board_id": "10",
                    "group_id": "topics",
                    "item_name": "Task",
                    "column_values": '{"status":{"label":"Done"}}',
                },
                {"create_item": {"id": "20"}},
                "create_item",
                "20",
            ),
            (
                "create_item_update",
                {"item_id": "20", "update_value": 'Done "today"'},
                {"create_update": {"id": "30"}},
                "create_update",
                "30",
            ),
            (
                "change_item_status",
                {"board_id": "10", "item_id": "20", "column_id": "status", "status_label": "Done"},
                {"change_column_value": {"id": "20", "name": "Task"}},
                "change_column_value",
                "20",
            ),
            (
                "change_item_column_value",
                {"board_id": "10", "item_id": "20", "column_id": "text", "value": "Updated"},
                {"change_simple_column_value": {"id": "20"}},
                "change_simple_column_value",
                "20",
            ),
        ]
        for method, parameters, data, query_field, expected_id in cases:
            with self.subTest(method=method):
                response = Response()
                response.status_code = 200
                response._content = json.dumps({"data": data}).encode()
                with patch(
                    "monday_sdk.graphql_handler.MondayGraphQL._send", return_value=response
                ) as send:
                    result = list(getattr(plugin, method)(**parameters))[0]
                self.assertIn(query_field, send.call_args.args[0])
                item = result[0] if isinstance(result, list) else result
                self.assertEqual(item["id"], expected_id)
                json.dumps(result)

        pages = []
        for data in [
            {
                "boards": [{"items_page": {"cursor": "next", "items": [{"id": "20"}]}}],
                "complexity": {"query": 0},
            },
            {
                "next_items_page": {"cursor": None, "items": [{"id": "21"}]},
                "complexity": {"query": 0},
            },
        ]:
            response = Response()
            response.status_code = 200
            response._content = json.dumps({"data": data}).encode()
            pages.append(response)
        with patch("monday_sdk.graphql_handler.MondayGraphQL._send", side_effect=pages):
            items = list(plugin.fetch_all_items_by_board_id(board_id="10", limit=1))[0]
        self.assertEqual([item["id"] for item in items], ["20", "21"])


if __name__ == "__main__":
    unittest.main()
