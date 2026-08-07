"""Tests for AWS Bedrock Knowledge Base Dify plugin endpoint."""

import json
from unittest.mock import MagicMock, patch

import pytest


class MockRequest:
    """Mock Werkzeug Request object."""

    def __init__(self, body=None):
        self._body = body
        self.method = "POST"
        self.url = "http://test/retrieval"
        self.headers = {"Authorization": "Bearer test"}

    def get_json(self):
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body


class TestKnowledgebaseRetrieval:
    """Tests for the Knowledgebaseretrieval endpoint."""

    def _get_endpoint(self):
        """Import and instantiate the endpoint class."""
        import sys
        import types

        # Mock the dify_plugin module
        mock_dify_plugin = types.ModuleType("dify_plugin")
        mock_dify_plugin.Endpoint = object
        mock_dify_plugin.config = types.ModuleType("dify_plugin.config")
        mock_dify_plugin.config.logger_format = types.ModuleType("dify_plugin.config.logger_format")
        mock_dify_plugin.config.logger_format.plugin_logger_handler = MagicMock(level=0)
        sys.modules["dify_plugin"] = mock_dify_plugin
        sys.modules["dify_plugin.config"] = mock_dify_plugin.config
        sys.modules["dify_plugin.config.logger_format"] = mock_dify_plugin.config.logger_format

        from endpoints.aws_bedrock_knowledge_base import Knowledgebaseretrieval

        return Knowledgebaseretrieval()

    @patch("boto3.client")
    def test_managed_search_configuration(self, mock_boto3):
        """Test that MANAGED type uses managedSearchConfiguration."""
        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200},
            "retrievalResults": [
                {
                    "content": {"text": "Test document"},
                    "score": 0.95,
                    "metadata": {"x-amz-bedrock-kb-source-uri": "s3://bucket/doc.pdf"},
                }
            ],
        }
        mock_boto3.return_value = mock_client

        endpoint = self._get_endpoint()
        request = MockRequest(body={
            "query": "What is managed KB?",
            "knowledge_id": "TESTMKB123",
            "retrieval_setting": {"top_k": 3, "score_threshold": 0.0},
        })
        settings = {
            "aws_access_key_id": "AKIATEST",
            "aws_secret_access_key": "secret",
            "region_name": "us-west-2",
            "knowledge_base_type": "MANAGED",
        }

        response = endpoint._invoke(request, {}, settings)
        result = json.loads(response.data)

        # Verify managedSearchConfiguration was used
        call_kwargs = mock_client.retrieve.call_args.kwargs
        assert "managedSearchConfiguration" in call_kwargs["retrievalConfiguration"]
        assert call_kwargs["retrievalConfiguration"]["managedSearchConfiguration"]["numberOfResults"] == 3

        # Verify results
        assert len(result["records"]) == 1
        assert result["records"][0]["content"] == "Test document"
        assert result["records"][0]["score"] == 0.95

    @patch("boto3.client")
    def test_vector_search_configuration(self, mock_boto3):
        """Test that VECTOR type uses vectorSearchConfiguration."""
        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200},
            "retrievalResults": [],
        }
        mock_boto3.return_value = mock_client

        endpoint = self._get_endpoint()
        request = MockRequest(body={
            "query": "test",
            "knowledge_id": "TEST123",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.0},
        })
        settings = {
            "aws_access_key_id": "AKIATEST",
            "aws_secret_access_key": "secret",
            "region_name": "us-east-1",
            "knowledge_base_type": "VECTOR",
        }

        endpoint._invoke(request, {}, settings)

        call_kwargs = mock_client.retrieve.call_args.kwargs
        assert "vectorSearchConfiguration" in call_kwargs["retrievalConfiguration"]
        assert call_kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]["overrideSearchType"] == "HYBRID"

    @patch("boto3.client")
    def test_default_to_vector(self, mock_boto3):
        """Test that missing knowledge_base_type defaults to VECTOR."""
        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200},
            "retrievalResults": [],
        }
        mock_boto3.return_value = mock_client

        endpoint = self._get_endpoint()
        request = MockRequest(body={
            "query": "test",
            "knowledge_id": "TEST123",
            "retrieval_setting": {"top_k": 3, "score_threshold": 0.0},
        })
        settings = {
            "aws_access_key_id": "AKIATEST",
            "aws_secret_access_key": "secret",
            "region_name": "us-west-2",
            # No knowledge_base_type — should default to VECTOR
        }

        endpoint._invoke(request, {}, settings)

        call_kwargs = mock_client.retrieve.call_args.kwargs
        assert "vectorSearchConfiguration" in call_kwargs["retrievalConfiguration"]

    @patch("boto3.client")
    def test_session_token_passed(self, mock_boto3):
        """Test that session token is passed to boto3 client when provided."""
        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200},
            "retrievalResults": [],
        }
        mock_boto3.return_value = mock_client

        endpoint = self._get_endpoint()
        request = MockRequest(body={
            "query": "test",
            "knowledge_id": "TEST123",
            "retrieval_setting": {"top_k": 3, "score_threshold": 0.0},
        })
        settings = {
            "aws_access_key_id": "ASIATEST",
            "aws_secret_access_key": "secret",
            "aws_session_token": "FwoGZXIvYXdzEBY...",
            "region_name": "us-west-2",
            "knowledge_base_type": "MANAGED",
        }

        endpoint._invoke(request, {}, settings)

        # Verify session token was passed to boto3.client
        client_call_kwargs = mock_boto3.call_args.kwargs
        assert client_call_kwargs["aws_session_token"] == "FwoGZXIvYXdzEBY..."

    @patch("boto3.client")
    def test_no_session_token(self, mock_boto3):
        """Test that session token is NOT passed when not provided."""
        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200},
            "retrievalResults": [],
        }
        mock_boto3.return_value = mock_client

        endpoint = self._get_endpoint()
        request = MockRequest(body={
            "query": "test",
            "knowledge_id": "TEST123",
            "retrieval_setting": {"top_k": 3, "score_threshold": 0.0},
        })
        settings = {
            "aws_access_key_id": "AKIATEST",
            "aws_secret_access_key": "secret",
            "region_name": "us-west-2",
        }

        endpoint._invoke(request, {}, settings)

        client_call_kwargs = mock_boto3.call_args.kwargs
        assert "aws_session_token" not in client_call_kwargs

    def test_empty_body_returns_empty_records(self):
        """Test that missing/empty body returns empty records gracefully."""
        endpoint = self._get_endpoint()
        request = MockRequest(body=None)
        settings = {"aws_access_key_id": "test", "aws_secret_access_key": "test", "region_name": "us-east-1"}

        response = endpoint._invoke(request, {}, settings)
        result = json.loads(response.data)
        assert result == {"records": []}

    @patch("boto3.client")
    def test_empty_knowledge_id_returns_empty(self, mock_boto3):
        """Test that empty knowledge_id returns empty records."""
        endpoint = self._get_endpoint()
        request = MockRequest(body={
            "query": "test",
            "knowledge_id": "",
            "retrieval_setting": {"top_k": 3},
        })
        settings = {"aws_access_key_id": "test", "aws_secret_access_key": "test", "region_name": "us-east-1"}

        response = endpoint._invoke(request, {}, settings)
        result = json.loads(response.data)
        assert result == {"records": []}
        mock_boto3.assert_not_called()

    @patch("boto3.client")
    def test_score_threshold_filtering(self, mock_boto3):
        """Test that results below score threshold are filtered out."""
        mock_client = MagicMock()
        mock_client.retrieve.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200},
            "retrievalResults": [
                {"content": {"text": "High score"}, "score": 0.9, "metadata": {"x-amz-bedrock-kb-source-uri": "s3://a"}},
                {"content": {"text": "Low score"}, "score": 0.3, "metadata": {"x-amz-bedrock-kb-source-uri": "s3://b"}},
            ],
        }
        mock_boto3.return_value = mock_client

        endpoint = self._get_endpoint()
        request = MockRequest(body={
            "query": "test",
            "knowledge_id": "TEST123",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
        })
        settings = {"aws_access_key_id": "test", "aws_secret_access_key": "test", "region_name": "us-west-2"}

        response = endpoint._invoke(request, {}, settings)
        result = json.loads(response.data)
        assert len(result["records"]) == 1
        assert result["records"][0]["content"] == "High score"

    @patch("boto3.client")
    def test_agentic_retrieve_stream(self, mock_boto3):
        """Test that agentic retrieval stream processes events correctly."""
        mock_client = MagicMock()
        mock_client.agentic_retrieve_stream.return_value = {
            "stream": [
                {"result": {"results": [
                    {"content": {"text": "Agentic result 1"}, "score": 0.95, "metadata": {}, "location": {"type": "S3", "s3Location": {"uri": "s3://bucket/doc1.pdf"}}},
                    {"content": {"text": "Agentic result 2"}, "score": 0.85, "metadata": {}, "location": {"type": "WEB", "webLocation": {"url": "https://example.com"}}},
                ]}}
            ]
        }
        mock_boto3.return_value = mock_client

        endpoint = self._get_endpoint()
        request = MockRequest(body={
            "query": "What is managed KB?",
            "knowledge_id": "TESTMKB123",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.0},
        })
        settings = {
            "aws_access_key_id": "AKIATEST",
            "aws_secret_access_key": "secret",
            "region_name": "us-west-2",
            "knowledge_base_type": "MANAGED",
            "use_agentic_retrieval": "Yes",
        }

        response = endpoint._invoke(request, {}, settings)
        result = json.loads(response.data)

        # Verify agentic retrieval was called
        mock_client.agentic_retrieve_stream.assert_called_once()
        # Standard retrieve should NOT be called (agentic succeeded)
        mock_client.retrieve.assert_not_called()

        # Verify results
        assert len(result["records"]) == 2
        assert result["records"][0]["content"] == "Agentic result 1"
        assert result["records"][0]["score"] == 0.95
        assert result["records"][0]["title"] == "s3://bucket/doc1.pdf"
        assert result["records"][1]["content"] == "Agentic result 2"
        assert result["records"][1]["title"] == "https://example.com"

    @patch("boto3.client")
    def test_agentic_retrieve_fallback(self, mock_boto3):
        """Test that agentic retrieval falls back to standard retrieve on failure."""
        mock_client = MagicMock()
        mock_client.agentic_retrieve_stream.side_effect = Exception("SDK too old")
        mock_client.retrieve.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200},
            "retrievalResults": [
                {"content": {"text": "Fallback result"}, "score": 0.8, "metadata": {}},
            ],
        }
        mock_boto3.return_value = mock_client

        endpoint = self._get_endpoint()
        request = MockRequest(body={
            "query": "test fallback",
            "knowledge_id": "TESTMKB123",
            "retrieval_setting": {"top_k": 3, "score_threshold": 0.0},
        })
        settings = {
            "aws_access_key_id": "AKIATEST",
            "aws_secret_access_key": "secret",
            "region_name": "us-west-2",
            "knowledge_base_type": "MANAGED",
            "use_agentic_retrieval": "Yes",
        }

        response = endpoint._invoke(request, {}, settings)
        result = json.loads(response.data)

        # Agentic was attempted then fell back
        mock_client.agentic_retrieve_stream.assert_called_once()
        mock_client.retrieve.assert_called_once()

        # Verify fallback results returned
        assert len(result["records"]) == 1
        assert result["records"][0]["content"] == "Fallback result"
