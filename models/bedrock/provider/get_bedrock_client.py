from collections.abc import Mapping

import boto3
from botocore.config import Config

from dify_plugin.errors.model import InvokeBadRequestError


def get_bedrock_client(service_name: str, credentials: Mapping[str, str]):
    region_name = credentials.get("aws_region")
    if not region_name:
        raise InvokeBadRequestError("aws_region is required")

    # Get endpoint URL and proxy URL
    bedrock_endpoint_url = credentials.get("bedrock_endpoint_url")
    bedrock_proxy_url = credentials.get("bedrock_proxy_url")

    # Check if both endpoint URL and proxy URL are provided
    if bedrock_endpoint_url and bedrock_proxy_url:
        raise InvokeBadRequestError("Cannot use both bedrock_endpoint_url and bedrock_proxy_url at the same time. Please choose one or none.")

    # Initialize client config with region
    client_config = Config(region_name=region_name)

    # Configure proxy if provided
    if bedrock_proxy_url:
        client_config.proxies = {
            'http': 'http://' + bedrock_proxy_url,
            'https': 'http://' + bedrock_proxy_url
        }

    # Get AWS credentials
    aws_access_key_id = credentials.get("aws_access_key_id")
    aws_secret_access_key = credentials.get("aws_secret_access_key")

    # Initialize client parameters
    client_kwargs = {
        'service_name': service_name,
        'config': client_config
    }

    # Add endpoint URL if provided
    if bedrock_endpoint_url and service_name == 'bedrock-runtime':
        client_kwargs['endpoint_url'] = bedrock_endpoint_url

    # Add credentials if provided
    if aws_access_key_id and aws_secret_access_key:
        client_kwargs['aws_access_key_id'] = aws_access_key_id
        client_kwargs['aws_secret_access_key'] = aws_secret_access_key

    # Create and return the client
    client = boto3.client(**client_kwargs)
    return client
