import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from provider.vanna import VannaProvider
from tools.vanna import VannaTool


class VannaCompatibilityTest(unittest.TestCase):
    def test_remote_training_and_sqlite_query(self):
        calls = []

        def post(url, *, headers, data):
            self.assertEqual(url, "https://vanna.example/rpc")
            self.assertEqual(headers["Vanna-Key"], "test-key")
            payload = json.loads(data)
            calls.append(payload)
            method = payload["method"]
            if method == "get_related_training_data":
                result = {"questions": [], "ddl": [], "documentation": []}
            elif method == "submit_prompt":
                result = {"data": "SELECT name FROM customers"}
            elif method == "get_training_data":
                result = {"data": '[{"id":"old-training"}]'}
            else:
                result = {"success": True, "message": "ok"}
                if method != "remove_training_data":
                    result["id"] = "new-training"
            return Mock(json=lambda: {"result": result})

        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "example.sqlite")
            with sqlite3.connect(database) as connection:
                connection.executescript(
                    "CREATE TABLE customers(name TEXT);" "INSERT INTO customers VALUES ('Ada');"
                )
            tool = VannaTool.from_credentials(
                {"api_key": "test-key", "base_url": "https://vanna.example/rpc/"}
            )
            with patch("requests.post", side_effect=post):
                messages = list(
                    tool._invoke(
                        {
                            "model": "example",
                            "prompt": "List customers",
                            "db_type": "SQLite",
                            "url": database,
                            "enable_training": True,
                            "reset_training_data": True,
                            "training_metadata": True,
                            "memos": "Customers are people.",
                        }
                    )
                )

        self.assertEqual(messages[0].message.text, "SELECT name FROM customers")
        self.assertIn("Ada", messages[1].message.text)
        methods = {call["method"] for call in calls}
        self.assertTrue({"remove_training_data", "add_ddl", "add_documentation"} <= methods)
        self.assertEqual(calls[-1]["params"][0]["question"], "List customers")
        self.assertEqual(calls[-1]["params"][0]["sql"], "SELECT name FROM customers")

    def test_credential_validation_supplies_prompt(self):
        with patch.object(VannaTool, "from_credentials") as create_tool:
            create_tool.return_value.invoke.return_value = iter(())
            VannaProvider()._validate_credentials({"api_key": "test-key"})
            parameters = create_tool.return_value.invoke.call_args.kwargs["tool_parameters"]
        self.assertIn("customers", parameters["prompt"])


if __name__ == "__main__":
    unittest.main()
