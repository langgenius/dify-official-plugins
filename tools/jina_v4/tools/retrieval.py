from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
import qdrant_client
from requests import post
import json


class Retrieval(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        query = tool_parameters.get("query")
        # em
        api_key = "jina_6ac82e222df142b6816b68f0f5f70fdbcCsR34Jw9EMFf4wdF5B-_pwNBmvp"
        base_url = "https://api.jina.ai/v1"
        if base_url.endswith("/"):
            base_url = base_url[:-1]
        url = f"{base_url}/embeddings"
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "model": "jina-embeddings-v4",
            "task": "text-matching",
            "input": [
                {"text": query}
            ],
        }
        response = post(url, headers=headers, data=json.dumps(data))
        resp = response.json()
        query_embedding = resp["data"][0]["embedding"]

        client = qdrant_client.QdrantClient(
            url="https://52db06fd-c330-4f8a-a087-4d28999eb86c.us-east4-0.gcp.cloud.qdrant.io",
            api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.VecCPKR39S74fUE76zQe8MIoqq-_00GaIYHyp8icXjs",
        )
        
        results = client.search(
            collection_name="jina-embeddings-v4",
            query_vector=query_embedding,
            limit=10,
            with_payload=True,
            with_vectors=True,
        )
        response = []
        for result in results:
            if result.payload is None:
                continue
            response.append({
                "content": result.payload.get("content", ""),
                "score": result.score,
            })

        yield self.create_variable_message("result", response)
