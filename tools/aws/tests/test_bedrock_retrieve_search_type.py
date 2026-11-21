import pytest

from tests import test_bedrock_image  # noqa: F401  (installs the fake dify_plugin modules)
import bedrock_retrieve  # noqa: E402

BedrockRetrieveTool = bedrock_retrieve.BedrockRetrieveTool


def test_invalid_search_type_reports_the_validation_error():
    tool = BedrockRetrieveTool.__new__(BedrockRetrieveTool)

    with pytest.raises(Exception) as excinfo:
        tool._bedrock_retrieve(
            bedrock_client=None,
            query_input="refund policy",
            knowledge_base_id="kb-1",
            num_results=3,
            search_type="BOGUS",
            rerank_model_id="default",
        )

    assert "search_type should be HYBRID or SEMANTIC" in str(excinfo.value)
    assert "RuntimeException" not in str(excinfo.value)
