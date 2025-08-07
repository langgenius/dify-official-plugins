from collections.abc import Generator
import json
from typing import Any
import re
import uuid

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
import qdrant_client
from requests import post
from qdrant_client.http.models import HnswConfigDiff


class Insert(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        input_text = tool_parameters.get("input_text")
        if not input_text:
            raise ValueError("input_text is required")
        
        pattern = r"!\[.*?\]\((.*?)\)"
        extracted_urls = re.findall(pattern, input_text)
        content = [input_text]
        for url in extracted_urls:
            print(url)
            content.append(url)

        # Jina Embedding v4
        api_key = "jina_6ac82e222df142b6816b68f0f5f70fdbcCsR34Jw9EMFf4wdF5B-_pwNBmvp"
        base_url = "https://api.jina.ai/v1"
        if base_url.endswith("/"):
            base_url = base_url[:-1]
        url = base_url + "/embeddings"
        headers = {
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        }
        input = [
            {
                "text": input_text,
            }
        ]
        for extracted_url in extracted_urls:
            input.append({
                "image": extracted_url,
            })

        data = {
            "model": "jina-embeddings-v4",
            "task": "text-matching",
            "truncate": True,
            "input": input,
        }
        print(json.dumps(data))
        response = post(url, headers=headers, data=json.dumps(data))
        resp = response.json()
        print(resp)
        embeddings = [item["embedding"] for item in resp["data"]]

        # insert to qdrant vdb
        client = qdrant_client.QdrantClient(
            url="https://52db06fd-c330-4f8a-a087-4d28999eb86c.us-east4-0.gcp.cloud.qdrant.io",
            api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.VecCPKR39S74fUE76zQe8MIoqq-_00GaIYHyp8icXjs",
        )
        from qdrant_client.http import models as rest

        vectors_config = rest.VectorParams(
            size=2048,
            distance=rest.Distance.COSINE,
        )
        hnsw_config = HnswConfigDiff(
            m=0,
            payload_m=16,
            ef_construct=100,
            full_scan_threshold=10000,
            max_indexing_threads=0,
            on_disk=False,
        )
        collections_response = client.get_collections()
        if "jina-embeddings-v4" not in collections_response.collections:
            client.create_collection(
                collection_name="jina-embeddings-v4",
                vectors_config=vectors_config,
                hnsw_config=hnsw_config,
            )

        points = [
            rest.PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "content": item,
                }
            )
            for embedding, item in zip(embeddings, content)
        ]
        client.upsert(
            collection_name="jina-embeddings-v4",
            points=points,
        )

        yield self.create_variable_message("result", "success")
