import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.cogvideo import CogVideoTool
from tools.cogview import CogViewTool

import httpx


class SDKTest(unittest.TestCase):
    def test_image_and_video_requests(self):
        requests = []

        def send(client, request, **kwargs):
            requests.append(request)
            if request.url.path.endswith("/images/generations"):
                data = {"data": [{"url": "https://example.com/image.png"}]}
            else:
                data = {"id": "video-id", "task_status": "SUCCESS", "video_result": []}
            return httpx.Response(200, json=data, request=request)

        credentials = {
            "zhipuai_api_key": "test-key",
            "zhipuai_base_url": "https://example.com/api/paas/v4/",
        }
        with patch.dict(os.environ, {"NO_PROXY": "", "no_proxy": ""}), patch.object(httpx.Client, "send", send):
            for tool, model in [(CogViewTool, "cogview-3"), (CogVideoTool, "cogvideox")]:
                messages = list(tool.from_credentials(credentials, user_id="user-id")._invoke(
                    {"model": model, "prompt": "A mountain", "size": "1024x1024"}
                ))
                self.assertTrue(messages)

        self.assertEqual([request.url.path for request in requests], [
            "/api/paas/v4/images/generations",
            "/api/paas/v4/videos/generations",
            "/api/paas/v4/async-result/video-id",
        ])
        for request in requests:
            self.assertEqual(request.url.host, "example.com")
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
        for request in requests[:2]:
            body = json.loads(request.content)
            self.assertEqual(body["prompt"], "A mountain")
            self.assertEqual(body["user_id"], "user-id")


if __name__ == "__main__":
    unittest.main()
