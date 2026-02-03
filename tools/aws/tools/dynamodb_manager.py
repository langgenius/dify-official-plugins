import json
from typing import Any
import boto3
from botocore.exceptions import ClientError
from collections.abc import Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DynamoDBManager(Tool):
    dynamodb_resource: Any = None
    dynamodb_client: Any = None

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        """
        invoke DynamoDB Manager operations
        """
        try:
            # Initialize DynamoDB client/resource if not already done
            if not self.dynamodb_resource or not self.dynamodb_client:
                aws_region = tool_parameters.get("aws_region", "us-east-1")
                self.dynamodb_resource = boto3.resource("dynamodb", region_name=aws_region)
                self.dynamodb_client = boto3.client("dynamodb", region_name=aws_region)

            operation_type = tool_parameters.get("operation_type")

            if operation_type == "create_table":
                result = self._create_table(tool_parameters)
            elif operation_type == "put_item":
                result = self._put_item(tool_parameters)
            elif operation_type == "get_item":
                result = self._get_item(tool_parameters)
            elif operation_type == "delete_item":
                result = self._delete_item(tool_parameters)
            elif operation_type == "scan":
                result = self._scan(tool_parameters)
            else:
                result = f"Unsupported operation: {operation_type}"

            if isinstance(result, dict):
                yield self.create_json_message(result)
            else:
                yield self.create_text_message(result)

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")

    def _create_table(self, params: dict) -> str:
        """Create DynamoDB table"""
        table_name = params.get("table_name")
        partition_key_name = params.get("partition_key_name", "id")
        sort_key_name = params.get("sort_key_name")
        
        key_schema = [{"AttributeName": partition_key_name, "KeyType": "HASH"}]
        attribute_definitions = [{"AttributeName": partition_key_name, "AttributeType": "S"}]
        
        if sort_key_name:
            key_schema.append({"AttributeName": sort_key_name, "KeyType": "RANGE"})
            attribute_definitions.append({"AttributeName": sort_key_name, "AttributeType": "S"})

        try:
            table = self.dynamodb_resource.create_table(
                TableName=table_name,
                KeySchema=key_schema,
                AttributeDefinitions=attribute_definitions,
                BillingMode="PAY_PER_REQUEST"
            )
            table.wait_until_exists()
            return f"Table {table_name} created successfully"
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceInUseException":
                return f"Table {table_name} already exists"
            else:
                raise e

    def _put_item(self, params: dict) -> str:
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
        
        table = self.dynamodb_resource.Table(table_name)
        table.put_item(Item=item)
        return f"Item added to {table_name} successfully"

    def _get_item(self, params: dict) -> str:
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
        
        table = self.dynamodb_resource.Table(table_name)

        response = table.get_item(
            Key=key_data
        )
        return response.get('Item')

    def _delete_item(self, params: dict) -> str:
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
        
        table = self.dynamodb_resource.Table(table_name)
        table.delete_item(Key=key_data)
        return f"Item deleted from {table_name} successfully"

    def _scan(self, params: dict) -> dict:
        """Scan DynamoDB table"""
        table_name = params.get("table_name")
        limit = params.get("limit", 100)
        
        table = self.dynamodb_resource.Table(table_name)
        response = table.scan(Limit=limit)
        
        return {
            "Items": response.get("Items", []),
            "Count": response.get("Count", 0),
            "ScannedCount": response.get("ScannedCount", 0)
        }
