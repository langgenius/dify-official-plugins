import json
from typing import Any, Union
from collections.abc import Generator

import boto3

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


# Define label mappings
LABEL_MAPPING = {0: "SAFE", 1: "NO_SAFE"}


class ContentModerationTool(Tool):
    sagemaker_endpoint: str = None

    def _invoke_sagemaker(self, payload: dict, endpoint: str, sagemaker_client):
        response = sagemaker_client.invoke_endpoint(
            EndpointName=endpoint,
            Body=json.dumps(payload),
            ContentType="application/json",
        )
        # Parse response
        response_body = response["Body"].read().decode("utf8")

        json_obj = json.loads(response_body)

        # Handle nested JSON if present
        if isinstance(json_obj, dict) and "body" in json_obj:
            body_content = json.loads(json_obj["body"])
            prediction_result = body_content.get("prediction")
        else:
            prediction_result = json_obj.get("prediction")

        # Map labels and return
        result = LABEL_MAPPING.get(
            prediction_result, "NO_SAFE"
        )  # If not found in mapping, default to NO_SAFE
        return result

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        """
        invoke tools
        """
        sagemaker_client = None
        try:
            # Build a fresh boto3 client per invocation so disk-refreshed
            # credentials (saml2aws login, aws sso login, IMDS) are picked
            # up without a plugin restart. Same fix as #3535 / #3545.
            aws_region = tool_parameters.get("aws_region")
            if aws_region:
                sagemaker_client = boto3.Session().client(
                    "sagemaker-runtime", region_name=aws_region
                )
            else:
                sagemaker_client = boto3.Session().client("sagemaker-runtime")

            if not self.sagemaker_endpoint:
                self.sagemaker_endpoint = tool_parameters.get("sagemaker_endpoint")

            content_text = tool_parameters.get("content_text")

            payload = {"text": content_text}

            result = self._invoke_sagemaker(
                payload, self.sagemaker_endpoint, sagemaker_client
            )

            yield self.create_text_message(text=result)

        except Exception as e:
            yield self.create_text_message(f"Exception {str(e)}")
