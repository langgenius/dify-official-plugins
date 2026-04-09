import json
from typing import Mapping
from llama_cloud.client import LlamaCloud
from werkzeug import Request, Response
from dify_plugin import Endpoint


class LlamacloudEndpoint(Endpoint):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        """
        Invokes the endpoint with the given request.
        """
        if settings.get("api_key"):
            if r.headers.get("Authorization") != f"Bearer {settings.get("api_key")}":
                return Response(
                    status=403,
                    content_type="application/json"
                )
        if not r.is_json:
            # first step of dify call is to check if the endpoint is available
            return Response(
                status=200,
                content_type="application/json"
            )

        # Parse JSON from the incoming request
        body = r.json

        pipeline_id = body.get("knowledge_id")
        query = body.get("query")

        # Extract retrieval settings with sensible defaults
        retrieval_settings = body.get("retrieval_setting", {})
        top_k = retrieval_settings.get("top_k")
        score_threshold = retrieval_settings.get("score_threshold")

        # Set up the LlamaCloud client using the API key from settings
        client_kwargs = {"token": settings.get("llama_cloud_api_key")}
        if settings.get("region") == "eu":
            client_kwargs["base_url"] = "https://api.cloud.eu.llamaindex.ai"
        client = LlamaCloud(**client_kwargs)

        # Execute the run_search pipeline
        # (Ensure that `pipeline_id` exists in your `settings` object)
        response = client.pipelines.run_search(
            pipeline_id=pipeline_id,
            query=query
        )

        results = []
        for node in response.retrieval_nodes:
            if node.score < retrieval_settings.get(score_threshold,.0):
                continue
            result = {
                "metadata": {
                    "path": node.node.extra_info.get('file_path', ''),
                    "description": node.node.extra_info.get('file_name', '')
                },
                "score": node.score,
                "title": node.node.extra_info.get('file_name', ''),
                "content": node.node.text
            }
            results.append(result)
            results=results[:top_k]

        # Construct and return the response
        return Response(
            response=json.dumps({"records": results}),
            status=200,
            content_type="application/json"
        )
