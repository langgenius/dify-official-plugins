"""Regression tests for the boto3 client construction in Bedrock-family tools.

Covers the fix from issue #3544 (the same `ExpiredTokenException` bug
that was fixed for the bedrock model plugin in PR #3535 / #3519):
`boto3.client(...)` uses the default session which caches credentials
in-process, so a `saml2aws login` / `aws sso login` / IMDS refresh after
the plugin process started never reaches the Bedrock client.

The fix builds the client from a fresh `boto3.Session()` on every
invocation. In `bedrock_retrieve.py` and `bedrock_retrieve_and_generate.py`
the on-instance `self.bedrock_client` cache was also removed, since
even a fresh session would be ignored once the instance held a stale
client.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add the tools dir to sys.path so the tool modules can import.
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

# Stub the dify_plugin SDK so the tool modules import without booting
# the SDK. Same pattern used in tools/aws/tests/__init__.py-equivalent
# fixtures across this repo.
_dify_plugin = sys.modules.get("dify_plugin") or type(sys)("dify_plugin")


class _FakeToolInvokeMessage:
    pass


class _FakeTool:
    def create_text_message(self, text: str):
        return ("text", text)


_dify_plugin.Tool = _FakeTool  # type: ignore[attr-defined]
_dify_plugin_entities = sys.modules.get("dify_plugin.entities") or type(sys)(
    "dify_plugin.entities"
)
_dify_plugin_entities_tool = sys.modules.get("dify_plugin.entities.tool") or type(sys)(
    "dify_plugin.entities.tool"
)
_dify_plugin_entities_tool.ToolInvokeMessage = _FakeToolInvokeMessage
_dify_plugin.entities = _dify_plugin_entities  # type: ignore[attr-defined]
_dify_plugin.entities.tool = _dify_plugin_entities_tool  # type: ignore[attr-defined]
sys.modules.setdefault("dify_plugin", _dify_plugin)
sys.modules.setdefault("dify_plugin.entities", _dify_plugin_entities)
sys.modules.setdefault("dify_plugin.entities.tool", _dify_plugin_entities_tool)

# The three tools import boto3 at module scope; we patch boto3.Session
# per-test instead of stubbing the import.

apply_guardrail = importlib.import_module("apply_guardrail")
bedrock_retrieve = importlib.import_module("bedrock_retrieve")
bedrock_retrieve_and_generate = importlib.import_module("bedrock_retrieve_and_generate")


def _patched_boto3_session() -> tuple[MagicMock, MagicMock]:
    """Replace boto3.Session with a mock that returns a mock session.

    Returns (session_cls, session_mock). Each call to boto3.Session()
    returns a fresh MagicMock that exposes .client(...).
    """
    session_mock = MagicMock(name="boto3.Session")
    client_mock = MagicMock(name="boto3.Session.client")
    session_mock.client.return_value = client_mock
    session_cls = MagicMock(name="boto3.client", return_value=session_mock)
    return session_cls, session_mock, client_mock


def _consume(generator):
    """Drain a Tool._invoke generator and return the list of messages."""
    return list(generator)


class TestApplyGuardrailUsesFreshSession:
    def test_each_invoke_creates_a_fresh_boto3_session(self) -> None:
        """apply_guardrail's _invoke must call boto3.Session() (not
        boto3.client) so the default-session credential cache is
        bypassed on every call.
        """
        tool = apply_guardrail.ApplyGuardrailTool.__new__(
            apply_guardrail.ApplyGuardrailTool
        )
        tool.runtime = MagicMock()
        tool.session = MagicMock()
        tool.create_text_message = _FakeTool().create_text_message

        with patch.object(
            apply_guardrail.boto3, "Session", return_value=MagicMock()
        ) as session_cls:
            mock_session = session_cls.return_value
            mock_session.client.return_value = MagicMock(
                apply_guardrail=MagicMock(
                    return_value={"action": "NONE", "outputs": [], "assessments": []}
                )
            )
            params = {
                "guardrail_id": "g1",
                "guardrail_version": "v1",
                "source": "INPUT",
                "text": "hello",
                "aws_region": "us-east-1",
            }
            _consume(tool._invoke(tool_parameters=params))

        session_cls.assert_called_once()
        mock_session.client.assert_called_once()

    def test_does_not_call_default_boto3_client(self) -> None:
        """Sanity: the fixed path must NOT go through boto3.client()."""
        tool = apply_guardrail.ApplyGuardrailTool.__new__(
            apply_guardrail.ApplyGuardrailTool
        )
        tool.runtime = MagicMock()
        tool.session = MagicMock()
        tool.create_text_message = _FakeTool().create_text_message

        with (
            patch.object(
                apply_guardrail.boto3, "client", return_value=MagicMock()
            ) as default_client,
            patch.object(apply_guardrail.boto3, "Session", return_value=MagicMock()),
        ):
            mock_session = apply_guardrail.boto3.Session.return_value
            mock_session.client.return_value = MagicMock(
                apply_guardrail=MagicMock(
                    return_value={"action": "NONE", "outputs": [], "assessments": []}
                )
            )
            params = {
                "guardrail_id": "g1",
                "guardrail_version": "v1",
                "source": "INPUT",
                "text": "hello",
                "aws_region": "us-east-1",
            }
            _consume(tool._invoke(tool_parameters=params))

        default_client.assert_not_called()


class TestBedrockRetrieveRemovesInstanceCache:
    def test_does_not_assign_self_bedrock_client(self) -> None:
        """bedrock_retrieve previously cached the client on self.bedrock_client,
        which combined with the default-session credential cache made
        ExpiredTokenException sticky. The fix removes the cache.
        """
        tool = bedrock_retrieve.BedrockRetrieveTool.__new__(
            bedrock_retrieve.BedrockRetrieveTool
        )
        tool.runtime = MagicMock()
        tool.session = MagicMock()
        tool.create_text_message = _FakeTool().create_text_message
        # Pre-set the attribute to assert it stays None (not re-cached).
        tool.bedrock_client = None

        with patch.object(
            bedrock_retrieve.boto3, "Session", return_value=MagicMock()
        ) as session_cls:
            mock_session = session_cls.return_value
            mock_session.client.return_value = MagicMock(
                retrieve=MagicMock(return_value={"retrievalResults": []})
            )
            params = {
                "aws_region": "us-east-1",
                "knowledge_base_id": "kb1",
                "retrieval_query": "test",
            }
            # We don't care about the full result; just verify self.bedrock_client
            # remains None after the invoke.
            try:
                _consume(tool._invoke(tool_parameters=params))
            except Exception:
                # The mocked retrieve response may not be fully fleshed out;
                # the assertion below is what we care about.
                pass

        assert tool.bedrock_client is None, (
            "bedrock_retrieve must not cache the boto3 client on self; "
            "the cache combined with the default-session credential cache "
            "made ExpiredTokenException sticky (see #3544, #3535)."
        )

    def test_bedrock_retrieve_session_uses_bedrock_agent_runtime(self) -> None:
        """The fresh session must call client(service_name='bedrock-agent-runtime')
        — the service the tool actually uses, not bedrock-runtime.
        """
        tool = bedrock_retrieve.BedrockRetrieveTool.__new__(
            bedrock_retrieve.BedrockRetrieveTool
        )
        tool.runtime = MagicMock()
        tool.session = MagicMock()
        tool.create_text_message = _FakeTool().create_text_message

        with patch.object(
            bedrock_retrieve.boto3, "Session", return_value=MagicMock()
        ) as session_cls:
            mock_session = session_cls.return_value
            mock_session.client.return_value = MagicMock(
                retrieve=MagicMock(return_value={"retrievalResults": []})
            )
            params = {
                "aws_region": "us-east-1",
                "knowledge_base_id": "kb1",
                "retrieval_query": "test",
            }
            try:
                _consume(tool._invoke(tool_parameters=params))
            except Exception:
                pass

        mock_session.client.assert_called_once()
        kwargs = mock_session.client.call_args.kwargs
        assert kwargs.get("service_name") == "bedrock-agent-runtime"


class TestBedrockRetrieveAndGenerateRemovesInstanceCache:
    def test_does_not_assign_self_bedrock_client(self) -> None:
        """Same fix as bedrock_retrieve: remove the on-instance client cache."""
        tool = bedrock_retrieve_and_generate.BedrockRetrieveAndGenerateTool.__new__(
            bedrock_retrieve_and_generate.BedrockRetrieveAndGenerateTool
        )
        tool.runtime = MagicMock()
        tool.session = MagicMock()
        tool.create_text_message = _FakeTool().create_text_message
        tool.bedrock_client = None

        with patch.object(
            bedrock_retrieve_and_generate.boto3, "Session", return_value=MagicMock()
        ) as session_cls:
            mock_session = session_cls.return_value
            mock_session.client.return_value = MagicMock(
                retrieve_and_generate=MagicMock(
                    return_value={"output": {"text": ""}, "citations": []}
                )
            )
            params = {"aws_region": "us-east-1", "input": "hi"}
            try:
                _consume(tool._invoke(tool_parameters=params))
            except Exception:
                pass

        assert tool.bedrock_client is None, (
            "bedrock_retrieve_and_generate must not cache the boto3 client on self."
        )
