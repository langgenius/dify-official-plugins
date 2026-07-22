from pathlib import Path
from unittest.mock import Mock

from conftest import ROOT, pytest_collection_modifyitems


def test_live_gate_ignores_other_providers(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", " ")
    gemini = Mock(path=ROOT / "models/tests/test_live.py")
    other = Mock(path=Path(ROOT).parent / "openai/tests/live/test_llm.py")
    gemini.get_closest_marker.return_value = object()
    other.get_closest_marker.return_value = object()

    pytest_collection_modifyitems([gemini, other])

    gemini.add_marker.assert_called_once()
    other.add_marker.assert_not_called()
