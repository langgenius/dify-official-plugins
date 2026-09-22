import json
import unittest
from unittest.mock import patch

import httpx2
import pandas as pd
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from client.vanna import (
    TrainingData,
    VannaClient,
    extract_sql,
    metadata_documents,
    sql_prompt,
)
from provider.vanna import VannaProvider


class VannaClientTest(unittest.TestCase):
    def test_rpc_protocol_and_unicode(self):
        calls = []
        responses = {
            "get_related_training_data": {
                "questions": [{"question": "客户？", "sql": "SELECT 1"}],
                "ddl": ["CREATE TABLE 客户(id INT)"],
                "documentation": ["客户包括新客户。"],
            },
            "submit_prompt": {"data": "SELECT '客户'"},
            "get_training_data": {"data": '[{"id":"旧资料"}]'},
        }

        def respond(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), "https://tenant.example:8443/v1/rpc?region=cn")
            self.assertEqual(request.headers["Vanna-Key"], "secret-key")
            self.assertEqual(request.headers["Vanna-Org"], "customers")
            self.assertEqual(request.headers["Content-Type"], "application/json")
            body = json.loads(request.content)
            self.assertEqual(set(body), {"method", "params"})
            calls.append(body)
            result = responses.get(body["method"], {"success": True, "id": "new", "message": "ok"})
            return httpx2.Response(200, json={"result": result})

        messages = [{"role": "user", "content": '客户 "名字"\n是什么？'}]
        with httpx2.Client(transport=httpx2.MockTransport(respond)) as http:
            client = VannaClient(
                http, "secret-key", "customers", "https://tenant.example:8443/v1/rpc?region=cn"
            )
            related = client.related_training("客户？")
            self.assertEqual(related.ddl, ["CREATE TABLE 客户(id INT)"])
            self.assertEqual(client.submit_prompt(messages), "SELECT '客户'")
            self.assertEqual(client.training_data()["id"].tolist(), ["旧资料"])
            client.remove_training("旧资料")
            client.add_ddl("CREATE TABLE 客户(id INT)")
            client.add_documentation("客户包括新客户。")
            client.add_sql("客户？", "SELECT 1")

        self.assertEqual(
            calls,
            [
                {"method": "get_related_training_data", "params": [{"question": "客户？"}]},
                {
                    "method": "submit_prompt",
                    "params": [{"data": json.dumps(messages, ensure_ascii=False)}],
                },
                {"method": "get_training_data", "params": []},
                {"method": "remove_training_data", "params": [{"data": "旧资料"}]},
                {"method": "add_ddl", "params": [{"data": "CREATE TABLE 客户(id INT)"}]},
                {"method": "add_documentation", "params": [{"data": "客户包括新客户。"}]},
                {
                    "method": "add_sql",
                    "params": [
                        {"question": "客户？", "sql": "SELECT 1", "tag": "Manually Trained"}
                    ],
                },
            ],
        )
        self.assertEqual(json.loads(calls[1]["params"][0]["data"]), messages)

    def test_training_data_accepts_pandas_json_orientations(self):
        for data in ('[{"id":"one"},{"id":"two"}]', '{"id":{"0":"one","1":"two"}}'):
            with self.subTest(data=data):
                transport = httpx2.MockTransport(
                    lambda request, data=data: httpx2.Response(200, json={"result": {"data": data}})
                )
                with httpx2.Client(transport=transport) as http:
                    self.assertEqual(
                        VannaClient(http, "key").training_data()["id"].tolist(), ["one", "two"]
                    )

    def test_credential_validation_is_read_only_and_keeps_custom_endpoint(self):
        for endpoint in (
            "https://tenant.service.example.co.uk:8443/custom/rpc?region=eu&mode=legacy",
            "https://tenant.example/rpc%2Ftenant?key=a%2Fb",
            "https://tenant.example/rpc%25tenant?key=a%2Fb",
            "http://127.0.0.1:8080/service/rpc",
            "http://localhost:8080/service/rpc",
        ):
            with self.subTest(endpoint=endpoint):
                requests = []

                def respond(request, requests=requests):
                    requests.append(request)
                    return httpx2.Response(200, json={"result": {"organizations": []}})

                http = httpx2.Client(transport=httpx2.MockTransport(respond))
                credentials = {"api_key": "secret-key", "base_url": endpoint}
                with patch("provider.vanna.httpx2.Client", return_value=http):
                    VannaProvider()._validate_credentials(credentials)

                self.assertEqual(len(requests), 1)
                self.assertEqual(str(requests[0].url), endpoint)
                self.assertEqual(
                    json.loads(requests[0].content), {"method": "list_my_models", "params": []}
                )
                self.assertEqual(requests[0].headers["Vanna-Key"], "secret-key")
                self.assertEqual(credentials, {"api_key": "secret-key", "base_url": endpoint})

    def test_default_endpoint_and_preserved_trailing_slash(self):
        for endpoint, expected in (
            (None, "https://ask.vanna.ai/rpc"),
            ("https://tenant.example/rpc/?region=eu", "https://tenant.example/rpc/?region=eu"),
            (
                "https://tenant.example/rpc%2Ftenant/?key=a%2Fb",
                "https://tenant.example/rpc%2Ftenant/?key=a%2Fb",
            ),
        ):
            with self.subTest(endpoint=endpoint):

                def respond(request, expected=expected):
                    self.assertEqual(str(request.url), expected)
                    return httpx2.Response(200, json={"result": {"organizations": []}})

                with httpx2.Client(transport=httpx2.MockTransport(respond)) as http:
                    VannaClient(http, "key", endpoint=endpoint).validate_credentials()

    def test_same_origin_redirect_preserves_post_body_and_credentials(self):
        for status in (307, 308):
            with self.subTest(status=status):
                requests = []

                def respond(request, requests=requests, status=status):
                    requests.append(request)
                    if len(requests) == 1:
                        return httpx2.Response(status, headers={"Location": "/rpc/?region=eu"})
                    return httpx2.Response(200, json={"result": {"data": "SELECT 1"}})

                with httpx2.Client(transport=httpx2.MockTransport(respond)) as http:
                    client = VannaClient(
                        http, "secret-key", "private-model", "https://tenant.example:8443/rpc"
                    )
                    self.assertEqual(
                        client.submit_prompt([{"role": "user", "content": "客户？"}]), "SELECT 1"
                    )

                self.assertEqual(len(requests), 2)
                self.assertEqual(str(requests[1].url), "https://tenant.example:8443/rpc/?region=eu")
                self.assertEqual(requests[1].content, requests[0].content)
                for request in requests:
                    self.assertEqual(request.method, "POST")
                    self.assertEqual(request.headers["Vanna-Key"], "secret-key")
                    self.assertEqual(request.headers["Vanna-Org"], "private-model")

    def test_cross_origin_redirect_is_rejected_before_sending_credentials(self):
        for destination in (
            "https://other.example/rpc",
            "http://tenant.example/rpc",
            "https://tenant.example:8443/rpc",
        ):
            with self.subTest(destination=destination):
                requests = []

                def respond(request, requests=requests, destination=destination):
                    requests.append(request)
                    return httpx2.Response(307, headers={"Location": destination})

                with (
                    httpx2.Client(transport=httpx2.MockTransport(respond)) as http,
                    self.assertRaisesRegex(ValueError, "different origin"),
                ):
                    VannaClient(
                        http, "secret-key", endpoint="https://tenant.example/rpc"
                    ).validate_credentials()
                self.assertEqual(len(requests), 1)
                self.assertEqual(str(requests[0].url), "https://tenant.example/rpc")

    def test_redirect_loop_is_bounded(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx2.Response(307, headers={"Location": "/rpc"})

        with (
            httpx2.Client(transport=httpx2.MockTransport(respond)) as http,
            self.assertRaisesRegex(ValueError, "Too many"),
        ):
            VannaClient(
                http, "secret-key", endpoint="https://tenant.example/rpc"
            ).validate_credentials()
        self.assertEqual(len(requests), 6)

    def test_rpc_credentials_are_not_attached_to_database_downloads(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx2.Response(200, json={"result": {"organizations": []}})

        with httpx2.Client(transport=httpx2.MockTransport(respond)) as http:
            VannaClient(http, "secret-key", "private-model").validate_credentials()
            http.get("https://databases.example/sample.sqlite")
        self.assertEqual(requests[0].headers["Vanna-Key"], "secret-key")
        self.assertNotIn("Vanna-Key", requests[1].headers)
        self.assertNotIn("Vanna-Org", requests[1].headers)

    def test_http_rpc_and_business_errors_are_not_successes(self):
        cases = [
            (401, {"result": {"success": True}}, httpx2.HTTPStatusError),
            (500, {"result": {"success": True}}, httpx2.HTTPStatusError),
            (200, {"error": {"message": "bad key"}}, ValueError),
            (200, {"error": "denied", "result": {"success": True}}, ValueError),
            (200, {}, ValueError),
            (200, [], ValueError),
            (200, {"result": None}, ValueError),
            (200, {"result": {"success": False, "message": "permission denied"}}, ValueError),
            (200, {"result": {"message": "missing success"}}, ValueError),
        ]
        for status, payload, error_type in cases:
            with self.subTest(status=status, payload=payload):
                transport = httpx2.MockTransport(
                    lambda request, status=status, payload=payload: httpx2.Response(
                        status, json=payload
                    )
                )
                with httpx2.Client(transport=transport) as http, self.assertRaises(error_type):
                    VannaClient(http, "key").add_ddl("CREATE TABLE customers(id INT)")

    def test_malformed_result_data_is_rejected(self):
        cases = [
            ("submit_prompt", {"data": []}),
            ("related_training", {"questions": [], "ddl": "not a list", "documentation": []}),
            ("training_data", {"data": "not json"}),
            ("validate_credentials", {"organizations": "not a list"}),
        ]
        for operation, result in cases:
            with self.subTest(operation=operation):
                transport = httpx2.MockTransport(
                    lambda request, result=result: httpx2.Response(200, json={"result": result})
                )
                with httpx2.Client(transport=transport) as http:
                    client = VannaClient(http, "key")
                    arguments = (
                        [[]]
                        if operation == "submit_prompt"
                        else ["question"]
                        if operation == "related_training"
                        else []
                    )
                    with self.assertRaises(ValueError):
                        getattr(client, operation)(*arguments)

    def test_provider_rejects_missing_key_and_failed_authentication(self):
        with patch("provider.vanna.httpx2.Client") as client:
            with self.assertRaises(ToolProviderCredentialValidationError):
                VannaProvider()._validate_credentials({})
            client.assert_not_called()
        transport = httpx2.MockTransport(
            lambda request: httpx2.Response(401, json={"error": "unauthorized"})
        )
        http = httpx2.Client(transport=transport)
        with (
            patch("provider.vanna.httpx2.Client", return_value=http),
            self.assertRaises(ToolProviderCredentialValidationError),
        ):
            VannaProvider()._validate_credentials({"api_key": "bad-key"})

    def test_invalid_endpoint_and_non_json_response_fail_clearly(self):
        with httpx2.Client(
            transport=httpx2.MockTransport(
                lambda request: httpx2.Response(200, text="upstream unavailable")
            )
        ) as http:
            for endpoint in ("file:///tmp/rpc", "ftp://tenant.example/rpc", "tenant.example/rpc"):
                with (
                    self.subTest(endpoint=endpoint),
                    self.assertRaisesRegex(ValueError, "HTTP or HTTPS"),
                ):
                    VannaClient(http, "key", endpoint=endpoint)
            with self.assertRaises(ValueError):
                VannaClient(http, "key").validate_credentials()

    def test_sql_only_training_can_generate_a_question(self):
        sql = "SELECT count(*) FROM customers"

        def respond(request):
            body = json.loads(request.content)
            self.assertEqual(body["method"], "submit_prompt")
            messages = json.loads(body["params"][0]["data"])
            self.assertEqual([message["role"] for message in messages], ["system", "user"])
            self.assertIn("Return just the question", messages[0]["content"])
            self.assertEqual(messages[1]["content"], sql)
            return httpx2.Response(200, json={"result": {"data": "How many customers?"}})

        with httpx2.Client(transport=httpx2.MockTransport(respond)) as http:
            self.assertEqual(VannaClient(http, "key").question_for_sql(sql), "How many customers?")


class VannaPromptTest(unittest.TestCase):
    def test_sql_response_formats_keep_complete_statements(self):
        cases = [
            ("SELECT 'a;b' AS value;", "SELECT 'a;b' AS value;"),
            ("SELECT 1;\nThis returns the first customer.", "SELECT 1;"),
            ("SELECT 1; DROP TABLE customers;", "SELECT 1;"),
            ("```sql\nSELECT 'a;b' AS value;\n```", "SELECT 'a;b' AS value;"),
            ("```sql\nSELECT 1;\nThis returns the first customer.\n```", "SELECT 1;"),
            ("```sql\nSELECT 1; DROP TABLE customers;\n```", "SELECT 1;"),
            ("```\nSELECT 1\n```", "SELECT 1"),
            (
                "WITH customers AS (SELECT 1 AS id) SELECT * FROM customers;",
                "WITH customers AS (SELECT 1 AS id) SELECT * FROM customers;",
            ),
            (
                "-- intermediate_sql\nSELECT DISTINCT name FROM customers",
                "-- intermediate_sql\nSELECT DISTINCT name FROM customers",
            ),
            ("Here is the query:\nSELECT 'a;b' AS value;", "SELECT 'a;b' AS value;"),
            (
                "Use this query:\nWITH customers AS (SELECT 1 AS id) SELECT * FROM customers;",
                "WITH customers AS (SELECT 1 AS id) SELECT * FROM customers;",
            ),
            ("Not enough schema information.", "Not enough schema information."),
        ]
        for response, sql in cases:
            with self.subTest(response=response):
                self.assertEqual(extract_sql(response), sql)

    def test_prompt_retains_context_examples_and_current_question(self):
        training = TrainingData(
            questions=[
                None,
                {},
                {"question": "missing SQL"},
                {"question": None, "sql": "SELECT 1"},
                {"question": "旧问题", "sql": "SELECT 2"},
            ],
            ddl=["CREATE TABLE customers(name TEXT)"],
            documentation=["Only active customers count."],
        )
        messages = sql_prompt("当前问题", "SQLite", training)
        self.assertEqual(
            [message["role"] for message in messages], ["system", "user", "assistant", "user"]
        )
        self.assertIn("SQLite", messages[0]["content"])
        self.assertIn(training.ddl[0], messages[0]["content"])
        self.assertIn(training.documentation[0], messages[0]["content"])
        self.assertIn("intermediate_sql", messages[0]["content"])
        self.assertEqual(
            messages[1:],
            [
                {"role": "user", "content": "旧问题"},
                {"role": "assistant", "content": "SELECT 2"},
                {"role": "user", "content": "当前问题"},
            ],
        )
        self.assertEqual(training.documentation, ["Only active customers count."])

    def test_prompt_skips_oversized_context_without_dropping_later_context(self):
        training = TrainingData(
            questions=[],
            ddl=["x" * 56000, "CREATE TABLE small(id INT)"],
            documentation=["Use small."],
        )
        prompt = sql_prompt("Count", "SQL", training)[0]["content"]
        self.assertNotIn("x" * 56000, prompt)
        self.assertIn("CREATE TABLE small(id INT)", prompt)
        self.assertIn("Use small.", prompt)

    def test_metadata_groups_quoted_identifiers_without_evaluation(self):
        columns = [
            "TABLE_CATALOG",
            "TABLE_SCHEMA",
            "TABLE_NAME",
            "COLUMN_NAME",
            "DATA_TYPE",
            "COMMENT",
            "IGNORED",
        ]
        frame = pd.DataFrame(
            [
                ['db"quoted', "schema'quoted", "customers", "id", "INT", "key", "omit"],
                ['db"quoted', "schema'quoted", "customers", "name", "TEXT", "display", "omit"],
                ['db"quoted', "other", "customers", "other_id", "INT", "key", "omit"],
                ["another", "public", "orders", "order_id", "INT", "key", "omit"],
            ],
            columns=columns,
        )
        documents = metadata_documents(frame)
        self.assertEqual(len(documents), 3)
        self.assertIn('customers table in the db"quoted database', documents[0])
        self.assertIn("schema'quoted", documents[0])
        self.assertIn("name", documents[0])
        self.assertNotIn("other_id", documents[0])
        self.assertIn("other_id", documents[1])
        self.assertIn("orders table in the another database", documents[2])
        self.assertTrue(all("IGNORED" not in document for document in documents))
        with self.assertRaisesRegex(ValueError, "catalog, schema and table"):
            metadata_documents(pd.DataFrame({"TABLE_NAME": ["customers"]}))


if __name__ == "__main__":
    unittest.main()
