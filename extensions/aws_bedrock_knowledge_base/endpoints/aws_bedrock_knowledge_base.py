import json
import boto3
from botocore.config import Config
import botocore
from werkzeug.wrappers import Request, Response
from dify_plugin import Endpoint
from typing import Mapping
import logging
from dify_plugin.config.logger_format import plugin_logger_handler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


def log(msg):
    logger.info(msg)


def _get_source_uri(result):
    """Extract source URI from a retrieval result, handling all location types."""
    location = result.get('location') or {}
    loc_type = location.get('type', '')
    if loc_type == 'S3' or 's3Location' in location:
        return (location.get('s3Location') or {}).get('uri', '')
    elif loc_type == 'WEB' or 'webLocation' in location:
        return (location.get('webLocation') or {}).get('url', '')
    elif 'confluenceLocation' in location:
        return (location.get('confluenceLocation') or {}).get('url', '')
    elif 'salesforceLocation' in location:
        return (location.get('salesforceLocation') or {}).get('url', '')
    elif 'sharePointLocation' in location:
        return (location.get('sharePointLocation') or {}).get('url', '')
    elif 'customDocumentLocation' in location:
        return (location.get('customDocumentLocation') or {}).get('id', '')
    # Fallback to metadata._source_uri (for agentic results)
    return (result.get('metadata') or {}).get('_source_uri', '')


class Knowledgebaseretrieval(Endpoint):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        log("Knowledge base retrieval invoked.22")
        
        try:
            body = r.get_json()
        except Exception as e:
            log(f"Failed to parse JSON: {e}")
            return Response(
                response=json.dumps({"records": []}),
                status=200,
                content_type="application/json"
            )
        
        log(f"Request: method={r.method}, url={r.url}, headers={dict(r.headers)}, data={body}")

        retrieval_setting = body.get('retrieval_setting')
        query = body.get('query')
        knowledge_id = body.get('knowledge_id')

        log(f"Received request - knowledge_id: {knowledge_id}, query: {query}, retrieval_setting: {retrieval_setting}")

        if not knowledge_id:
            log("knowledge_id is empty, returning empty records")
            return Response(
                response=json.dumps({"records": []}),
                status=200,
                content_type="application/json"
            )

        client_kwargs = {
            "aws_access_key_id": settings.get("aws_access_key_id"),
            "aws_secret_access_key": settings.get("aws_secret_access_key"),
            "region_name": settings.get("region_name"),
        }
        if settings.get("aws_session_token"):
            client_kwargs["aws_session_token"] = settings.get("aws_session_token")
        client = boto3.client("bedrock-agent-runtime", config=Config(user_agent_extra="dify/bedrock-kb"), **client_kwargs)

        try:
            # Try agentic retrieval if enabled
            use_agentic = settings.get("use_agentic_retrieval", "Yes")
            if use_agentic == "Yes":
                try:
                    log(f"Attempting agentic retrieval for knowledgeBaseId: {knowledge_id}")
                    agentic_response = client.agentic_retrieve_stream(
                        knowledgeBaseId=knowledge_id,
                        messages=[{"content": {"text": query}, "role": "user"}],
                        retrievers=[{
                            "configuration": {
                                "knowledgeBase": {
                                    "knowledgeBaseId": knowledge_id,
                                    "retrievalOverrides": {
                                        "maxNumberOfResults": (retrieval_setting or {}).get("top_k", 5)
                                    },
                                }
                            }
                        }],
                        agenticRetrieveConfiguration={
                            "foundationModelType": "MANAGED",
                            "rerankingModelType": "MANAGED",
                        },
                    )

                    results = []
                    event_stream = agentic_response.get("stream", [])
                    for event in event_stream:
                        if "result" in event and "results" in event["result"]:
                            for retrieval_result in event["result"]["results"]:
                                score = retrieval_result.get("score", 1.0)
                                threshold = (retrieval_setting or {}).get("score_threshold", 0.0) or 0.0
                                if score < threshold:
                                    continue
                                result = {
                                    "metadata": retrieval_result.get("metadata") or {},
                                    "score": score,
                                    "title": _get_source_uri(retrieval_result),
                                    "content": (retrieval_result.get("content") or {}).get("text", ""),
                                }
                                results.append(result)

                    if results:
                        log(f"Agentic retrieval returned {len(results)} results")
                        return Response(
                            response=json.dumps({"records": results}),
                            status=200,
                            content_type="application/json",
                        )
                    log("Agentic retrieval returned no results, falling back to standard retrieve")
                except Exception as e:
                    log(f"Agentic retrieval failed ({e}), falling back to standard retrieve")

            # Determine retrieval configuration based on knowledge base type
            kb_type = settings.get("knowledge_base_type", "VECTOR")
            top_k = (retrieval_setting or {}).get("top_k", 5)
            if kb_type == "MANAGED":
                retrieval_config = {
                    "managedSearchConfiguration": {"numberOfResults": top_k}
                }
            else:
                retrieval_config = {
                    "vectorSearchConfiguration": {"numberOfResults": top_k,
                                                  "overrideSearchType": "HYBRID"}
                }

            log(f"Calling bedrock-agent-runtime retrieve API with knowledgeBaseId: {knowledge_id}, type: {kb_type}")
            response = client.retrieve(
                knowledgeBaseId=knowledge_id,
                retrievalConfiguration=retrieval_config,
                retrievalQuery={"text": query},
            )

            log(f"API response status: {response.get('ResponseMetadata', {}).get('HTTPStatusCode')}")

            results = []
            if response.get("ResponseMetadata") and response.get("ResponseMetadata").get("HTTPStatusCode") == 200:
                if response.get("retrievalResults"):
                    retrieval_results = response.get("retrievalResults")
                    log(f"Retrieved {len(retrieval_results)} results from knowledge base")
                    for retrieval_result in retrieval_results:
                        # filter out results with score less than threshold
                        score = retrieval_result.get("score", 0.0) or 0.0
                        threshold = (retrieval_setting or {}).get("score_threshold", 0.0) or 0.0
                        if score < threshold:
                            continue
                        result = {
                            "metadata": retrieval_result.get("metadata") or {},
                            "score": score,
                            "title": _get_source_uri(retrieval_result) or (retrieval_result.get("metadata") or {}).get("x-amz-bedrock-kb-source-uri", ""),
                            "content": (retrieval_result.get("content") or {}).get("text", ""),
                        }
                        results.append(result)

            log(f"Returning {len(results)} results after filtering")
            return Response(
                response=json.dumps({"records": results}),
                status=200,
                content_type="application/json"
            )

        except botocore.exceptions.ClientError as error:
            error_code = error.response['Error']['Code']
            log(f"AWS ClientError: {error_code} - {error.response['Error'].get('Message')}")
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



