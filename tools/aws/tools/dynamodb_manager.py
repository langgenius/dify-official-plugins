import json
from typing import Any
import boto3
from botocore.exceptions import ClientError
from collections.abc import Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


def _build_dynamodb_resource(credentials: dict) -> Any:
    """Build a fresh DynamoDB resource from a new ``boto3.Session``.

    Mirrors the per-call ``boto3.Session()`` pattern from
    ``tools/aws`` PR #3545 (Bedrock family) and the in-progress
    boto3 batch under issue #3544. boto3's default session caches
    credentials in-process, so a ``saml2aws login`` /
    ``aws sso login`` / IMDS refresh after the plugin process
    started never reaches the cached client. Building a fresh
    session on every invocation picks up the new credentials.
    """
    aws_region = credentials.get("aws_region", "us-east-1")
    return boto3.Session(region_name=aws_region).resource("dynamodb")


class DynamoDBManager(Tool):
    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        """
        invoke DynamoDB Manager operations
        """
        try:
            # Build a fresh resource per invocation so disk-refreshed
            # credentials are picked up on every call. See issue #3544.
            dynamodb_resource = _build_dynamodb_resource(tool_parameters)
            operation_type = tool_parameters.get("operation_type")

            if operation_type == "create_table":
                result = self._create_table(tool_parameters, dynamodb_resource)
            elif operation_type == "put_item":
                result = self._put_item(tool_parameters, dynamodb_resource)
            elif operation_type == "get_item":
                result = self._get_item(tool_parameters, dynamodb_resource)
            elif operation_type == "delete_item":
                result = self._delete_item(tool_parameters, dynamodb_resource)
            elif operation_type == "scan":
                result = self._scan(tool_parameters, dynamodb_resource)
            else:
                result = f"Unsupported operation: {operation_type}"

            if isinstance(result, dict):
                yield self.create_json_message(result)
            else:
                yield self.create_text_message(result)

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")

    def _create_table(self, params: dict, dynamodb_resource: Any) -> str:
        """Create DynamoDB table"""
        table_name = params.get("table_name")
        partition_key_name = params.get("partition_key_name", "id")
        sort_key_name = params.get("sort_key_name")

        key_schema = [{"AttributeName": partition_key_name, "KeyType": "HASH"}]
        attribute_definitions = [
            {"AttributeName": partition_key_name, "AttributeType": "S"}
        ]

        if sort_key_name:
            key_schema.append({"AttributeName": sort_key_name, "KeyType": "RANGE"})
            attribute_definitions.append(
                {"AttributeName": sort_key_name, "AttributeType": "S"}
            )

        try:
            table = dynamodb_resource.create_table(
                TableName=table_name,
                KeySchema=key_schema,
                AttributeDefinitions=attribute_definitions,
                BillingMode="PAY_PER_REQUEST",
            )
            table.wait_until_exists()
            return f"Table {table_name} created successfully"
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceInUseException":
                return f"Table {table_name} already exists"
            else:
                raise e

    def _put_item(self, params: dict, dynamodb_resource: Any) -> str:
        """Put item into DynamoDB table"""
        table_name = params.get("table_name")
        partition_key_name = params.get("partition_key_name")
        partition_key = params.get("partition_key")
        sort_key_name = params.get("sort_key_name")
        sort_key = params.get("sort_key")
        item_data = params.get("item_data")

        item = {}
        item[partition_key_name] = partition_key

        if sort_key_name and sort_key:
            item[sort_key_name] = sort_key

        if isinstance(item_data, str):
            item_data = json.loads(item_data)

        item.update(item_data)

        table = dynamodb_resource.Table(table_name)
        table.put_item(Item=item)
        return f"Item added to {table_name} successfully"

    def _get_item(self, params: dict, dynamodb_resource: Any) -> str:
        """Get item from DynamoDB table"""
        table_name = params.get("table_name")
        partition_key_name = params.get("partition_key_name")
        partition_key = params.get("partition_key")
        sort_key = params.get("sort_key")
        sort_key_name = params.get("sort_key_name")

        # Build key data
        key_data = {}
        key_data[partition_key_name] = partition_key

        if sort_key_name and sort_key:
            key_data[sort_key_name] = sort_key

        table = dynamodb_resource.Table(table_name)

        response = table.get_item(Key=key_data)
        return response.get("Item")

    def _delete_item(self, params: dict, dynamodb_resource: Any) -> str:
        """Delete item from DynamoDB table"""
        table_name = params.get("table_name")
        partition_key = params.get("partition_key")
        sort_key = params.get("sort_key")
        partition_key_name = params.get("partition_key_name", "id")
        sort_key_name = params.get("sort_key_name")

        # Build key data
        key_data = {}
        key_data[partition_key_name] = partition_key

        if sort_key_name and sort_key:
            key_data[sort_key_name] = sort_key

        table = dynamodb_resource.Table(table_name)
        table.delete_item(Key=key_data)
        return f"Item deleted from {table_name} successfully"

    def _scan(self, params: dict, dynamodb_resource: Any) -> dict:
        """Scan DynamoDB table"""
        table_name = params.get("table_name")
        limit = params.get("limit", 100)

        table = dynamodb_resource.Table(table_name)
        response = table.scan(Limit=limit)

        return {
            "Items": response.get("Items", []),
            "Count": response.get("Count", 0),
            "ScannedCount": response.get("ScannedCount", 0),
        }
