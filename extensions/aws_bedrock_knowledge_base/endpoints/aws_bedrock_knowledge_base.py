import json
import boto3
import botocore
from werkzeug.wrappers import Request, Response
from dify_plugin import Endpoint
from typing import Mapping


class Knowledgebaseretrieval(Endpoint):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        body = r.get_json()

        retrieval_setting = body.get('retrieval_setting')
        query = body.get('query')
        knowledge_id = body.get('knowledge_id')

        client = boto3.client(
            "bedrock-agent-runtime",
            aws_secret_access_key=settings.get("aws_secret_access_key"),
            aws_access_key_id=settings.get("aws_access_key_id"),
            region_name=settings.get("region_name")
        )

        try:
            response = client.retrieve(
                knowledgeBaseId=knowledge_id,
                retrievalConfiguration={
                    "vectorSearchConfiguration": {"numberOfResults": retrieval_setting.get("top_k"),
                                                  "overrideSearchType": "HYBRID"}
                },
                retrievalQuery={"text": query},
            )

            results = []
            if response.get("ResponseMetadata") and response.get("ResponseMetadata").get("HTTPStatusCode") == 200:
                if response.get("retrievalResults"):
                    retrieval_results = response.get("retrievalResults")
                    for retrieval_result in retrieval_results:
                        # filter out results with score less than threshold
                        if retrieval_result.get("score") < retrieval_setting.get("score_threshold", .0):
                            continue
                        result = {
                            "metadata": retrieval_result.get("metadata"),
                            "score": retrieval_result.get("score"),
                            "title": retrieval_result.get("metadata").get("x-amz-bedrock-kb-source-uri"),
                            "content": retrieval_result.get("content").get("text"),
                        }
                        results.append(result)

            return Response(
                response=json.dumps({"records": results}),
                status=200,
                content_type="application/json"
            )

        except botocore.exceptions.ClientError as error:
            error_code = error.response['Error']['Code']
            if error_code == "InvalidSignatureException":
                return Response(
                    response=json.dumps({"error_code": 1002, "error_msg": "Wrong AWS secret access key"}),
                    status=400,
                    content_type="application/json"
                )
            elif error_code == "UnrecognizedClientException":
                return Response(
                    response=json.dumps({"error_code": 1002, "error_msg": "Wrong AWS secret access ID"}),
                    status=400,
                    content_type="application/json"
                )
            elif error_code == "ResourceNotFoundException":
                return Response(
                    response=json.dumps(
                        {"error_code": 2001, "error_msg": "Knowledge Base ID does not exist in this region"}),
                    status=400,
                    content_type="application/json"
                )
            elif error_code == "ValidationException":
                return Response(
                    response=json.dumps(
                        {"error_code": 2001, "error_msg": "Knowledge Base ID does not exist in this region"}),
                    status=400,
                    content_type="application/json"
                )
            else:
                return Response(
                    response=json.dumps({"error_code": 1002, "error_msg": "Unknown error occurred"}),
                    status=400,
                    content_type="application/json"
                )



