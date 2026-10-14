import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb
import httpx2

from tools.vanna import VannaTool


class VannaCompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = str(Path(self.directory.name) / "example.sqlite")
        with sqlite3.connect(self.database) as connection:
            connection.executescript(
                "CREATE TABLE customers(name TEXT); INSERT INTO customers VALUES ('Ada');"
            )
        self.calls = []
        self.prompts = []
        self.responses = ["SELECT name FROM customers"]
        self.training_json = '[{"id":"old-training"}]'
        self.endpoint = "https://private.example.co.uk:8443/custom/rpc?tenant=example"
        self.parameters = {
            "model": "example",
            "prompt": "List customers",
            "db_type": "SQLite",
            "url": self.database,
        }
        self.tool = VannaTool.from_credentials({"api_key": "test-key", "base_url": self.endpoint})

    def handle_rpc(self, request):
        self.assertEqual(str(request.url), self.endpoint)
        self.assertEqual(request.headers["Vanna-Key"], "test-key")
        self.assertEqual(request.headers["Vanna-Org"], "example")
        payload = json.loads(request.content)
        self.calls.append(payload)
        method = payload["method"]
        if method == "get_related_training_data":
            result = {
                "questions": [
                    {"question": "Count customers", "sql": "SELECT count(*) FROM customers"}
                ],
                "ddl": ["CREATE TABLE customers(name TEXT)"],
                "documentation": ["Customers are people."],
            }
        elif method == "submit_prompt":
            self.prompts.append(json.loads(payload["params"][0]["data"]))
            result = {"data": self.responses.pop(0)}
        elif method == "get_training_data":
            result = {"data": self.training_json}
        else:
            self.assertIn(
                method, {"add_ddl", "add_documentation", "add_sql", "remove_training_data"}
            )
            result = {"success": True, "message": "ok", "id": "new-training"}
        return httpx2.Response(200, json={"result": result})

    def invoke(self, **parameters):
        http = httpx2.Client(transport=httpx2.MockTransport(self.handle_rpc))
        try:
            with patch("tools.vanna.httpx2.Client", return_value=http):
                return list(self.tool._invoke(self.parameters | parameters))
        finally:
            http.close()

    def test_training_reset_metadata_explicit_training_and_output(self):
        messages = self.invoke(
            enable_training=True,
            reset_training_data=True,
            training_metadata=True,
            ddl="CREATE TABLE invoices(id INTEGER)",
            question="How many customers?",
            sql="SELECT count(*) FROM customers",
            memos="Use the customers table.",
        )
        self.assertEqual(
            [call["method"] for call in self.calls],
            [
                "get_training_data",
                "remove_training_data",
                "add_ddl",
                "add_ddl",
                "add_sql",
                "add_documentation",
                "get_related_training_data",
                "submit_prompt",
                "add_sql",
            ],
        )
        self.assertEqual(self.calls[1]["params"], [{"data": "old-training"}])
        ddls = [call["params"][0]["data"] for call in self.calls if call["method"] == "add_ddl"]
        self.assertEqual(
            ddls, ["CREATE TABLE customers(name TEXT)", "CREATE TABLE invoices(id INTEGER)"]
        )
        self.assertEqual(
            self.calls[4]["params"],
            [
                {
                    "question": "How many customers?",
                    "sql": "SELECT count(*) FROM customers",
                    "tag": "Manually Trained",
                }
            ],
        )
        self.assertEqual(
            self.calls[-1]["params"],
            [
                {
                    "question": "List customers",
                    "sql": "SELECT name FROM customers",
                    "tag": "Manually Trained",
                }
            ],
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].message.text, "SELECT name FROM customers")
        self.assertEqual(
            messages[1].message.text, "|    | name   |\n|---:|:-------|\n|  0 | Ada    |"
        )
        self.assertEqual(
            [message["role"] for message in self.prompts[0]],
            ["system", "user", "assistant", "user"],
        )
        self.assertIn("SQLite", self.prompts[0][0]["content"])
        self.assertIn("Customers are people.", self.prompts[0][0]["content"])

    def test_disabled_training_ignores_manual_options_but_keeps_auto_training(self):
        self.invoke(
            reset_training_data=True,
            training_metadata=True,
            ddl="ignored",
            memos="ignored",
            sql="ignored",
        )
        self.assertEqual(
            [call["method"] for call in self.calls],
            ["get_related_training_data", "submit_prompt", "add_sql"],
        )

    def test_sql_only_training_generates_question(self):
        self.responses.insert(0, "How many customers?")
        self.invoke(enable_training=True, sql="SELECT count(*) FROM customers")
        self.assertEqual(self.calls[0]["method"], "submit_prompt")
        self.assertIn("guess what the business question", self.prompts[0][0]["content"])
        self.assertEqual(self.calls[1]["params"][0]["question"], "How many customers?")

    def test_intermediate_query_requires_explicit_permission(self):
        self.responses = ["-- intermediate_sql\nSELECT name FROM customers"]
        with patch("tools.vanna.connect_database") as connect:
            database = connect.return_value.__enter__.return_value
            database.dialect = "SQLite"
            messages = self.invoke()
            database.run_sql.assert_not_called()
        self.assertEqual(len(messages), 1)
        self.assertIn("allow_llm_to_see_data=True", messages[0].message.text)
        self.assertEqual(
            [call["method"] for call in self.calls], ["get_related_training_data", "submit_prompt"]
        )
        self.assertNotIn("Ada", json.dumps(self.calls))

    def test_allowed_intermediate_query_supplies_rows_only_to_second_prompt(self):
        self.responses = [
            "-- intermediate_sql\nSELECT name FROM customers",
            "```sql\nSELECT name FROM customers WHERE name = 'Ada';\n```",
        ]
        messages = self.invoke(allow_llm_to_see_data=True)
        self.assertNotIn("Ada", json.dumps(self.prompts[0]))
        self.assertIn("|  0 | Ada", self.prompts[1][0]["content"])
        self.assertIn("results of the intermediate SQL query", self.prompts[1][0]["content"])
        self.assertEqual(messages[0].message.text, "SELECT name FROM customers WHERE name = 'Ada';")
        self.assertIn("Ada", messages[1].message.text)
        self.assertEqual(
            sum(call["method"] == "get_related_training_data" for call in self.calls), 1
        )

    def test_empty_query_returns_table_without_auto_training(self):
        self.responses = ["SELECT name FROM customers WHERE 1 = 0"]
        messages = self.invoke()
        self.assertEqual(len(messages), 2)
        self.assertIn("name", messages[1].message.text)
        self.assertNotIn("add_sql", [call["method"] for call in self.calls])

    def test_model_explanations_return_text_without_executing_or_training(self):
        for explanation in ("Not enough schema information.", "Unable to help with this query."):
            with self.subTest(explanation=explanation):
                self.responses = [explanation]
                self.calls.clear()
                with patch("tools.vanna.connect_database") as connect:
                    database = connect.return_value.__enter__.return_value
                    database.dialect = "SQLite"
                    messages = self.invoke()
                    database.run_sql.assert_not_called()
                self.assertEqual([message.message.text for message in messages], [explanation])
                self.assertNotIn("add_sql", [call["method"] for call in self.calls])

    def test_invalid_postgres_cannot_delete_remote_training_data(self):
        with (
            patch("psycopg2.connect", side_effect=RuntimeError("invalid database credentials")),
            self.assertRaisesRegex(RuntimeError, "invalid database credentials"),
        ):
            self.invoke(
                db_type="Postgres",
                url="db.example",
                db_name="analytics",
                username="reader",
                port=5432,
                enable_training=True,
                reset_training_data=True,
            )
        self.assertEqual(self.calls, [])

    def test_duckdb_metadata_training_and_query(self):
        path = str(Path(self.directory.name) / "example.duckdb")
        with duckdb.connect(path) as connection:
            connection.execute("CREATE TABLE customers(name VARCHAR)")
            connection.execute("INSERT INTO customers VALUES ('Ada')")
        messages = self.invoke(
            db_type="DuckDB", url=path, enable_training=True, training_metadata=True
        )
        documents = [
            call["params"][0]["data"]
            for call in self.calls
            if call["method"] == "add_documentation"
        ]
        self.assertEqual(len(documents), 1)
        self.assertIn("customers table", documents[0])
        self.assertIn("column_name", documents[0])
        self.assertIn("Ada", messages[1].message.text)

    def test_optional_nulls_use_defaults_and_input_errors_do_not_expose_password(self):
        messages = self.invoke(memos=None, port=None)
        self.assertIn("Ada", messages[1].message.text)
        with self.assertRaises(ValueError) as raised:
            self.invoke(db_type="Not a database", password="never-show-this")
        self.assertNotIn("never-show-this", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
