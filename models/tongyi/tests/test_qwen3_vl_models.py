"""Regression tests for exposing the Qwen3-VL embedding and reranker models in the Tongyi plugin.

Issue: https://github.com/langgenius/dify-official-plugins/issues/3828

Dify Model Studio / DashScope already provides ``qwen3-vl-embedding`` (a
multimodal text+image embedding) and ``qwen3-vl-rerank`` (a multimodal
reranker from the Qwen3-VL family), but the Tongyi provider did not
register the corresponding model files, which made them invisible in
Dify's Model Provider UI and unreachable through the plugin.

The fix adds two model YAML files:

- ``models/tongyi/models/text_embedding/qwen3-vl-embedding.yaml`` with
  the ``vision`` feature, so the existing ``_is_vision_model`` YAML
  introspection picks it up and routes it to ``embed_multimodal_documents``
  rather than the text-only path.
- ``models/tongyi/models/rerank/qwen3-vl-rerank.yaml`` (no Python code
  change needed: ``GTERerankModel._invoke`` already forwards ``model=model``
  to ``dashscope.TextReRank.call``, so any registered rerank model name
  reaches DashScope).

The rerank ``_position.yaml`` ordering is updated so the new model
appears first in the UI dropdown (the newest Qwen3-VL family member
sits above the older Qwen3-Rerank and GTE rerank entries).

These tests are pure file-system + YAML introspection — no network or
SDK load required. The ``_is_vision_model`` runtime assertion exercises
the actual YAML-driven vision detection against the new model.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from models.text_embedding import text_embedding as te  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parents[1]
EMBEDDING_YAML = ROOT_DIR / "models" / "text_embedding" / "qwen3-vl-embedding.yaml"
RERANK_YAML = ROOT_DIR / "models" / "rerank" / "qwen3-vl-rerank.yaml"
RERANK_POSITION_YAML = ROOT_DIR / "models" / "rerank" / "_position.yaml"


# ---------------------------------------------------------------------------
# File-system checks
# ---------------------------------------------------------------------------


def test_embedding_model_yaml_exists() -> None:
    """The qwen3-vl-embedding.yaml file must exist under models/text_embedding/."""
    assert EMBEDDING_YAML.is_file(), f"missing: {EMBEDDING_YAML}"


def test_rerank_model_yaml_exists() -> None:
    """The qwen3-vl-rerank.yaml file must exist under models/rerank/."""
    assert RERANK_YAML.is_file(), f"missing: {RERANK_YAML}"


# ---------------------------------------------------------------------------
# YAML schema
# ---------------------------------------------------------------------------


def test_embedding_yaml_has_vision_feature() -> None:
    """``qwen3-vl-embedding`` must declare ``vision`` so the multimodal route runs."""
    parsed = yaml.safe_load(EMBEDDING_YAML.read_text(encoding="utf-8"))
    assert parsed["model"] == "qwen3-vl-embedding"
    assert parsed["model_type"] == "text-embedding"
    assert "vision" in parsed.get("features", []), (
        "vision feature must be present so _is_vision_model routes the call to "
        "embed_multimodal_documents rather than the text-only path"
    )
    assert parsed["model_properties"]["context_size"] >= 1
    assert "pricing" in parsed
    assert "currency" in parsed["pricing"]


def test_rerank_yaml_has_rerank_type() -> None:
    """``qwen3-vl-rerank`` must declare ``model_type: rerank``."""
    parsed = yaml.safe_load(RERANK_YAML.read_text(encoding="utf-8"))
    assert parsed["model"] == "qwen3-vl-rerank"
    assert parsed["model_type"] == "rerank"
    assert parsed["model_properties"]["context_size"] >= 1


def test_rerank_position_yaml_includes_qwen3_vl_rerank() -> None:
    """The rerank ``_position.yaml`` must list the new model so the UI shows it."""
    parsed = yaml.safe_load(RERANK_POSITION_YAML.read_text(encoding="utf-8"))
    assert "qwen3-vl-rerank" in parsed, (
        "rerank _position.yaml must include qwen3-vl-rerank so it appears in the "
        "Dify Model Provider UI"
    )


# ---------------------------------------------------------------------------
# Runtime: _is_vision_model picks up the new YAML
# ---------------------------------------------------------------------------


def test_is_vision_model_recognises_qwen3_vl_embedding() -> None:
    """``_is_vision_model`` returns True for the new model name.

    This exercises the YAML-introspection path that ``TongyiTextEmbeddingModel
    ._invoke`` uses to decide between ``embed_documents`` and
    ``embed_multimodal_documents``. Without ``features: [vision]``, the new
    model would be routed to the text-only path and reject multimodal
    payloads with a validation error.
    """
    # Clear the cache populated by any prior test that ran _is_vision_model.
    te.vision_models.pop("qwen3-vl-embedding", None)
    assert te.TongyiTextEmbeddingModel._is_vision_model("qwen3-vl-embedding") is True