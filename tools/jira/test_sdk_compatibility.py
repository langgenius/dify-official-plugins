"""Run with `python -m unittest test_sdk_compatibility.py` from this plugin."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

import dify_plugin
import requests
import yaml

from tools.get_recent_projects import GetRecentProjectsTool
from tools.list_issue_type import ListIssueTypeTool
from tools.create_issue import CreateIssueTool


class JiraSdkTest(unittest.TestCase):
    def test_cloud_and_server_issue_descriptions(self):
        for token_type, version in [("Basic", "3"), ("Bearer", "2")]:
            with self.subTest(token_type=token_type):
                response = requests.Response()
                response.status_code = 201
                response._content = b'{"key":"DEMO-1"}'
                runtime = SimpleNamespace(
                    runtime=SimpleNamespace(credentials={"url": "https://jira.example.com", "token_type": token_type, "token": "test"}),
                    create_json_message=lambda data: data,
                )
                with patch.object(requests.Session, "send", return_value=response) as send:
                    result = list(CreateIssueTool._invoke(runtime, {"project_key": "1", "issue_type_id": "2", "summary": "Task", "description": "Hello"}))
                request = send.call_args.args[0]
                self.assertEqual(urlparse(request.url).path, f"/rest/api/{version}/issue")
                description = json.loads(request.body)["fields"]["description"]
                self.assertEqual(description["type"] if token_type == "Basic" else description, "doc" if token_type == "Basic" else "Hello")
                self.assertEqual(result, [{"key": "DEMO-1"}])

    def test_project_routes_use_resource_urls_and_project_keys(self):
        sent = []

        def send(session, request, **kwargs):
            sent.append(request)
            path = urlparse(request.url).path
            response = requests.Response()
            response.status_code = 200
            response.request = request
            data = {"id": "1", "key": "DEMO"}
            if path.endswith("/recent"):
                data = [data]
            elif path.endswith("/issuetypes"):
                data = {"values": [{"id": "2", "name": "Task"}]}
            response._content = json.dumps(data).encode()
            return response

        runtime = SimpleNamespace(
            runtime=SimpleNamespace(credentials={"url": "https://jira.example.com", "token": "test"}),
            create_json_message=lambda data: json.loads(json.dumps(data)),
        )
        with patch.object(requests.Session, "send", send):
            recent = list(GetRecentProjectsTool._invoke(runtime, {}))
            types = list(ListIssueTypeTool._invoke(runtime, {"project_key": "DEMO"}))
        self.assertEqual(recent[0]["total"], 1)
        self.assertEqual(types[0]["values"][0]["name"], "Task")
        self.assertEqual([urlparse(request.url).path for request in sent], [
            "/rest/api/2/project/recent", "/rest/api/2/project/DEMO", "/rest/api/2/issue/createmeta/DEMO/issuetypes",
        ])
        definition = yaml.safe_load(Path("tools/list_issue_type.yaml").read_text())
        self.assertEqual(definition["extra"]["python"]["source"], "tools/list_issue_type.py")


if __name__ == "__main__":
    unittest.main()
