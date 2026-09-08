"""Run with `python -m unittest test_sdk_compatibility.py` from this plugin."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import dify_plugin
import requests

from provider.confluence import ConfluenceProvider
from tools.create_page import CreatePageTool
from tools.get_page import GetPageTool
from tools.get_space import GetSpaceTool
from tools.list_page_of_space import ListPageofSpaceTool
from tools.list_space import ListSpaceTool
from tools.remove_page import RemovePageTool


class ConfluenceSdkTest(unittest.TestCase):
    def test_cloud_and_server_requests(self):
        for base_url, cloud in [("https://example.atlassian.net", True), ("https://confluence.example.com", False)]:
            with self.subTest(base_url=base_url):
                sent = []
                space = {"id": "1", "key": "DEMO", "name": "Demo"}
                page = {"id": "2", "title": "Page", "body": {"storage": {"value": "<p>Text</p>"}}}

                def send(session, request, **kwargs):
                    sent.append(request)
                    path = urlparse(request.url).path
                    response = requests.Response()
                    response.status_code = 204 if request.method == "DELETE" else 200
                    response.request = request
                    response.url = request.url
                    if path.endswith(("/spaces", "/space")):
                        data = {"results": [space], "size": 1, "limit": 100, "_links": {}}
                    elif path.endswith("/space/DEMO"):
                        data = space
                    elif path.endswith(("/pages", "/content")) and request.method == "GET":
                        data = {"results": [page], "size": 1, "limit": 100, "_links": {}}
                    else:
                        data = page
                    response._content = b"" if response.status_code == 204 else json.dumps(data).encode()
                    return response

                credentials = {"url": base_url, "username": "test@example.com", "token": "test"}
                runtime = SimpleNamespace(
                    runtime=SimpleNamespace(credentials=credentials),
                    create_text_message=lambda text: text,
                    create_json_message=lambda data: json.loads(json.dumps(data)),
                )
                with patch.object(requests.Session, "send", send):
                    ConfluenceProvider._validate_credentials(None, credentials)
                    spaces = list(ListSpaceTool._invoke(runtime, {}))
                    found_space = list(GetSpaceTool._invoke(runtime, {"space_key": "DEMO"}))
                    pages = list(ListPageofSpaceTool._invoke(runtime, {"space_key": "DEMO"}))
                    found_page = list(GetPageTool._invoke(runtime, {"page_id": "2"}))
                    created = list(CreatePageTool._invoke(runtime, {"space_key": "DEMO", "title": "Page", "body": "<p>Text</p>"}))
                    removed = list(RemovePageTool._invoke(runtime, {"page_id": "2"}))
                self.assertTrue(spaces[0]["spaces"])
                self.assertEqual(found_space[0], space)
                self.assertEqual(pages[0]["pages"], [page])
                self.assertEqual(found_page[0], page)
                self.assertEqual(created, ["Page created successfully"])
                self.assertEqual(removed, ["Page removed successfully"])
                post = next(request for request in sent if request.method == "POST")
                payload = json.loads(post.body)
                if cloud:
                    self.assertTrue(all("/wiki/api/v2/" in request.url for request in sent))
                    self.assertEqual(payload["spaceId"], "1")
                    self.assertEqual(payload["body"], {"storage": {"value": "<p>Text</p>"}})
                    self.assertTrue(any(parse_qs(urlparse(request.url).query).get("body-format") == ["storage"] for request in sent))
                    self.assertTrue(any(parse_qs(urlparse(request.url).query).get("space-id") == ["1"] for request in sent))
                    listing = next(request for request in sent if request.method == "GET" and urlparse(request.url).path.endswith("/pages"))
                    self.assertNotIn("body-format", parse_qs(urlparse(listing.url).query))
                else:
                    self.assertTrue(all("/rest/api/" in request.url for request in sent))
                    self.assertEqual(payload["space"], {"key": "DEMO"})


if __name__ == "__main__":
    unittest.main()
