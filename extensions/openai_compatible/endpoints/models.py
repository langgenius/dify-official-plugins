import json
from typing import Mapping
from werkzeug import Request, Response
from dify_plugin import Endpoint
from endpoints.auth import BaseAuth

class Models(Endpoint, BaseAuth):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        """
        返回模型列表，仿照 OpenaiCompatible 接口风格
        """
        try:
            models = [
                {
                    "id": settings.get("model_id"),
                    "object": "model",
                    "created": 1677610602,
                    "owned_by": "baibaomen",
                    "permission": []
                }
            ]
            result = {
                "object": "list",
                "data": models
            }
            return Response(
                json.dumps(result),
                status=200,
                content_type="application/json",
            )
        except ValueError as e:
            return Response(f"Error: {e}", status=400, content_type="text/plain")
        except Exception as e:
            return Response(f"Error: {e}", status=500, content_type="text/plain")