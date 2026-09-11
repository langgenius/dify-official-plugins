"""Run with `python -m unittest test_sdk_compatibility.py` from this plugin."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import dify_plugin  # Initialize the plugin runtime before importing HTTP clients.
import requests

from provider.smartsheet import SmartsheetProvider
from tools.add_rows import AddRowsTool
from tools.get_sheet_info import GetSheetInfoTool
from tools.update_rows import UpdateRowsTool


class SmartsheetSdkTest(unittest.TestCase):
    def test_row_requests_and_sheet_response(self):
        sent = []

        def send(session, request, **kwargs):
            sent.append(request)
            response = requests.Response()
            response.status_code = 200
            response.request = request
            data = {"id": 1, "name": "Tasks", "totalRowCount": 0, "rows": [],
                    "columns": [{"id": 2, "title": "Name", "type": "TEXT_NUMBER", "index": 0}]}
            if request.method != "GET":
                data = {"message": "SUCCESS", "resultCode": 0, "result": [{"id": 3}]}
            response._content = json.dumps(data).encode()
            return response

        runtime = SimpleNamespace(
            runtime=SimpleNamespace(credentials={"api_key": "test"}),
            create_text_message=lambda text: text,
            create_json_message=lambda data: json.loads(json.dumps(data)),
        )
        with patch.object(requests.Session, "send", send):
            added = list(AddRowsTool._invoke(runtime, {"sheet_id": "1", "row_data": '{"Name":"Task"}'}))
            updated = list(UpdateRowsTool._invoke(runtime, {"sheet_id": "1", "row_updates": '{"row_id":3,"Name":"Done"}'}))
            info = list(GetSheetInfoTool._invoke(runtime, {"sheet_id": "1"}))
        self.assertEqual(added[-1]["row_ids"], ["3"])
        self.assertEqual(updated[-1]["rows_updated"], 1)
        self.assertEqual(info[-1]["columns"][0]["type"], "TEXT_NUMBER")
        writes = [request for request in sent if request.method != "GET"]
        self.assertEqual(json.loads(writes[0].body), [{"toTop": True, "cells": [{"columnId": 2, "value": "Task"}]}])
        self.assertEqual(json.loads(writes[1].body), [{"id": 3, "cells": [{"columnId": 2, "value": "Done"}]}])
        self.assertTrue(all("include=" not in request.url for request in sent))

    def test_invalid_credentials_are_rejected(self):
        response = requests.Response()
        response.status_code = 401
        response._content = b'{"errorCode":1002,"message":"Invalid access token."}'
        with patch.object(requests.Session, "send", return_value=response):
            with self.assertRaises(dify_plugin.errors.tool.ToolProviderCredentialValidationError):
                SmartsheetProvider._validate_credentials(None, {"api_key": "invalid"})


if __name__ == "__main__":
    unittest.main()
