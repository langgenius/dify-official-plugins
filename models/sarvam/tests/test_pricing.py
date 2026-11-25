from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models" / "llm"

INR_AT_94 = {
    "sarvam-105b": (15, 60),
    "sarvam-105b-conversations": (15, 60),
    "glm5.3": (126, 390),
    "glm5.3-flash": (13.5, 45),
    "gemma4": (35, 90),
    "deepseekv4.1-flash-1017": (14, 55),
    "deepseekv4.1-flash-1017-interactive": (25, 105),
}


def pricing(name: str) -> dict:
    model = yaml.safe_load((MODELS_DIR / f"{name}.yaml").read_text())
    return model["pricing"]


@pytest.mark.parametrize(
    ("name", "inr_input", "inr_output"),
    [(name, values[0], values[1]) for name, values in INR_AT_94.items()],
)
def test_pricing_matches_inr_at_94(name: str, inr_input: float, inr_output: float) -> None:
    value = pricing(name)
    assert value["unit"] == "0.000001"
    assert value["currency"] == "USD"
    assert float(value["input"]) == pytest.approx(inr_input / 94, rel=1e-9)
    assert float(value["output"]) == pytest.approx(inr_output / 94, rel=1e-9)


def test_105b_uses_list_price_not_introductory() -> None:
    value = pricing("sarvam-105b")
    assert float(value["input"]) == pytest.approx(15 / 94)
    assert float(value["input"]) != pytest.approx(10 / 94)
    assert float(value["output"]) == pytest.approx(60 / 94)
    assert float(value["output"]) != pytest.approx(25 / 94)
