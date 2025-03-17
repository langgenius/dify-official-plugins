from typing import Any, Union
from urllib.parse import urlparse

import boto3
import json
import base64
from collections.abc import Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

class OpenSearchRetrieveTool(Tool):
    os_client: Any = None
    bedrock_client: Any = None
    s3_client: Any = None

    def _get_embedding(self, model_id:str, text:str=None, image_path:str=None, dimension:int=1024):
        image_base64 = None

        def parse_s3_url(s3_url:str):
            if s3_url.startswith("s3://"):
                s3_url = s3_url[5:]

            parts = s3_url.split('/', 1)
            
            if len(parts) == 2:
                bucket_name = parts[0]
                object_key = parts[1]
            else:
                bucket_name = parts[0]
                object_key = ''
            
            return bucket_name, object_key

        if image_path:
            try:
                bucket_name, object_key = parse_s3_url(image_path)
                response = self.s3_client.get_object(Bucket=bucket_name, Key=object_key)
                image_content = response['Body'].read()
                image_base64 = base64.b64encode(image_content).decode('utf-8')
            except Exception as e:
                self.create_text_message(f"'{image_path}' is not valid image path")
                pass

        request_body = {}
        if text:
            request_body["inputText"] = text

        if image_base64:
            request_body["inputImage"] = image_base64

        embedding_config = {
            "embeddingConfig": { 
                 "outputEmbeddingLength": dimension
            }
        }
        body = json.dumps({**request_body, **embedding_config})
        response = self.bedrock_client.invoke_model(
            body=body,
            modelId=model_id,
            accept="application/json",
            contentType="application/json")
        response_body = json.loads(response.get("body").read())
        return response_body.get("embedding")

    def _search_by_aos_knn(self, q_embedding, index_name:str, embedding_field:str, meta_field_list:list[str], size:int=5):
        query = {
            "size": size,
            "query": {
                "knn": {
                    f"{embedding_field}" : {
                        "vector": q_embedding,
                        "k": size
                    }
                }
            }
        }

        opensearch_knn_respose = []
        query_response = self.os_client.search(
            body=query,
            index=index_name
        )

        results = []
        for item in query_response["hits"]["hits"]:
            result_obj = { field_name: item['_source'][field_name] for field_name in meta_field_list }
            result_obj['score'] = item['_score']
            results.append(result_obj)

        return results

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        """
        invoke tools
        """
        try:
            aws_region = tool_parameters.get("aws_region")
            if not self.os_client:
                opensearch_endpoint = tool_parameters.get("opensearch_endpoint").replace("https://","")
                index_name = tool_parameters.get("index_name")

                credentials = boto3.Session().get_credentials()
                awsauth = AWSV4SignerAuth(credentials, aws_region, "aoss")

                # 创建 OpenSearch 客户端
                self.os_client = OpenSearch(
                    hosts=[{'host': opensearch_endpoint, 'port': 443}],
                    http_auth=awsauth,
                    use_ssl=True,
                    verify_certs=True,
                    connection_class=RequestsHttpConnection
                )
            if not self.s3_client:
                self.s3_client = boto3.client(service_name="s3", region_name=aws_region)

            if not self.bedrock_client:
                self.bedrock_client = boto3.client(service_name="bedrock-runtime", region_name=aws_region)

            emb_model_id = tool_parameters.get("embedding_model_id")
            embedding_field = tool_parameters.get("embedding_field")
            metadata_fields = tool_parameters.get("metadata_fields").split(",")
            image_s3_path = tool_parameters.get("image_s3_path")
            query_text = tool_parameters.get("query_text")
            vector_size = int(tool_parameters.get("vector_size"))
            topk = tool_parameters.get("topk")

            embedding = self._get_embedding(model_id=emb_model_id, 
                text=query_text, 
                image_path=image_s3_path, 
                dimension=vector_size
            )

            result = self._search_by_aos_knn(q_embedding=embedding, 
                index_name=index_name, 
                embedding_field=embedding_field, 
                meta_field_list=metadata_fields, 
                size=topk
            )

            yield self.create_json_message({"results":result})

        except Exception as e:
            yield self.create_text_message(f"Exception: {str(e)}")