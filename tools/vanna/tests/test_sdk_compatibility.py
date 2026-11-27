import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from provider.vanna import VannaProvider
from vanna.legacy.remote import VannaDefault

from tools.vanna import VannaTool


class VannaCompatibilityTest(unittest.TestCase):
    def test_oracle_query_without_vector_store_dependencies(self):
        client = VannaDefault(model="example", api_key="test-key")
        with patch("oracledb.connect") as connect:
            cursor = connect.return_value.cursor.return_value
            cursor.description = [("NAME",)]
            cursor.fetchall.return_value = [("Ada",)]
            client.connect_to_oracle(user="user", password="password", dsn="host:1521/service")
            result = client.run_sql("SELECT name FROM customers;")

        connect.assert_called_once_with(user="user", password="password", dsn="host:1521/service")
        cursor.execute.assert_called_once_with("SELECT name FROM customers")
        self.assertEqual(result["NAME"].tolist(), ["Ada"])

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
                    "CREATE TABLE customers(name TEXT);INSERT INTO customers VALUES ('Ada');"
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

    def test_credential_validation_lists_models_on_custom_endpoint(self):
        with patch("provider.vanna.VannaDefault") as client:
            client.return_value.get_models.return_value = ["example"]
            VannaProvider()._validate_credentials(
                {
                    "api_key": "test-key",
                    "base_url": "https://vanna.example/rpc/",
                }
            )
        client.assert_called_once_with(
            model="",
            api_key="test-key",
            config={"endpoint": "https://vanna.example/rpc"},
        )
        client.return_value.get_models.assert_called_once_with()

    def test_rejects_retired_hosted_endpoint(self):
        for endpoint in ("", "https://ask.vanna.ai/rpc"):
            with (
                self.subTest(endpoint=endpoint),
                self.assertRaisesRegex(ToolProviderCredentialValidationError, "hosted service has shut down"),
            ):
                VannaProvider()._validate_credentials({"api_key": "test-key", "base_url": endpoint})


if __name__ == "__main__":
    unittest.main()
