import json
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from requests import Response

from src.baserow import BaserowCredentials, BaserowPlugin


class BaserowCompatibilityTest(unittest.TestCase):
    def test_single_row_operations_and_json_values(self):
        plugin = BaserowPlugin(credentials=BaserowCredentials(token="test-key"))
        values = {"Name": "Ada", "Status": {"id": 7, "value": "Done", "color": "green"}}
        row = {"id": 2, "order": "1.0", **values}
        requests = []

        def request(*, method, url, headers, **kwargs):
            self.assertEqual(headers["Authorization"], "Token test-key")
            path = urlsplit(url).path
            requests.append((method, path, kwargs["json"]))
            if path == "/api/database/tables/all-tables/":
                body = [{"id": 1, "name": "Customers"}]
            elif path == "/api/database/fields/table/1/":
                body = [
                    {"id": 1, "name": "Name", "type": "text", "order": 0, "primary": True},
                    {
                        "id": 2,
                        "name": "Status",
                        "type": "single_select",
                        "order": 1,
                        "select_options": [values["Status"]],
                    },
                ]
            elif path == "/api/database/rows/table/1/" and method == "GET":
                body = {"results": [row], "next": None}
            else:
                self.assertIn(
                    path, {"/api/database/rows/table/1/", "/api/database/rows/table/1/2/"}
                )
                body = row
            response = Response()
            response.status_code = 200
            response._content = json.dumps(body).encode()
            return response

        with patch("requests.Session.request", side_effect=request):
            plugin.verify()
            self.assertEqual(list(plugin.get_tables())[0][0]["id"], 1)
            self.assertEqual(list(plugin.get_rows(table_id="1"))[0], [values])
            self.assertEqual(list(plugin.get_a_row(table_id="1", row_id="2"))[0], values)
            for method, parameters in [
                (plugin.create_a_row, {}),
                (plugin.update_a_row, {"row_id": "2"}),
            ]:
                output = list(
                    method(table_id="1", content='{"Name":"Ada","Status":7}', **parameters)
                )
                self.assertEqual(json.loads(json.dumps(output[0])), values)
            with self.assertRaises(TypeError):
                list(plugin.create_a_row(table_id="1", content='[{"Name":"Ada"}]'))

        writes = [call for call in requests if call[0] != "GET"]
        self.assertEqual(
            writes,
            [
                ("POST", "/api/database/rows/table/1/", {"Name": "Ada", "Status": 7}),
                ("PATCH", "/api/database/rows/table/1/2/", {"Name": "Ada", "Status": 7}),
            ],
        )


if __name__ == "__main__":
    unittest.main()
