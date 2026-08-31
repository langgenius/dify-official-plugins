"""Shared pytest fixtures for the bedrock plugin tests.

The bedrock plugin's AIModel subclasses require a `model_schemas`
list of `AIModelEntity` instances in their constructor. We don't
care about that field for the unit tests in this directory — we
exercise the error-handling branches of `_invoke` directly, with
the boto3 / Dify / AWS paths mocked — so the fixture supplies a
synthetic empty list.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make the bedrock package importable from the tests directory.
_PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PKG_ROOT))


@pytest.fixture
def make_llm(monkeypatch):
    """Return a factory that builds a BedrockLargeLanguageModel with
    stubbed-out dependencies.

    The base `LargeLanguageModel.__init__` pulls in AIModelEntity
    instances via `predefined_models()`; we patch that to return an
    empty list so the constructor doesn't try to resolve real model
    schemas. The runtime client lookup is also stubbed so the
    class-instantiation step doesn't touch AWS.
    """

    def _factory():
        # Stub the AIModel class hierarchy so the constructor doesn't
        # fail trying to resolve real predefined model schemas. We
        # also stub get_bedrock_client since `_invoke` calls it
        # eagerly via the inference-profile branch.
        from models.llm.llm import BedrockLargeLanguageModel  # type: ignore

        llm = BedrockLargeLanguageModel.__new__(BedrockLargeLanguageModel)
        # Mimic the state the base class would have set up.
        llm.runtime_client = MagicMock(name="runtime_client")
        llm.bedrock_client = MagicMock(name="bedrock_client")
        llm.bedrock_runtime_client = MagicMock(name="bedrock_runtime_client")
        return llm

    return _factory
