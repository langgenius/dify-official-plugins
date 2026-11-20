from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.errors.model import InvokeBadRequestError
from models.llm import chat, responses
from models.llm.llm import OpenAILargeLanguageModel
from models.common_openai import apply_gpt62_pricing


@pytest.mark.parametrize(
    ("prompt", "tier", "timestamp", "input_rate", "output_rate"),
    [
        (272_000, "default", None, "8", "40"),
        (272_001, "priority", None, "32", "120"),
        (272_001, "ultrafast", "2027-03-01T07:59:59", "48", "180"),
        (272_001, "ultrafast", "2027-03-01T08:00:00", "96", "360"),
    ],
)
def test_gpt62_usage_charges_each_token_once(
    prompt, tier, timestamp, input_rate, output_rate
):
    usage = LLMUsage.empty_usage()
    usage.prompt_tokens = prompt
    usage.completion_tokens = 7
    usage.prompt_unit_price = Decimal("8")
    usage.completion_unit_price = Decimal("40")
    usage.prompt_price_unit = usage.completion_price_unit = Decimal("0.000001")
    details = {
        "cached_tokens": 4_000,
        "cache_write_tokens": 7_000,
        "cache_write_tokens_details": {
            "ttl_30m_tokens": 3_000,
            "ttl_12h_tokens": 4_000,
        },
    }
    created = (
        datetime.fromisoformat(timestamp).replace(tzinfo=UTC).timestamp()
        if timestamp
        else None
    )
    result = apply_gpt62_pricing(usage, "gpt-6.2-astra", details, tier, created)
    assert result.prompt_tokens == prompt
    assert (
        result.prompt_price
        == Decimal(input_rate) * (prompt - 11_000 + 200 + 3_750 + 10_000) / 1_000_000
    )
    assert result.completion_price == Decimal(output_rate) * 7 / 1_000_000
    assert result.total_price == result.prompt_price + result.completion_price


@pytest.mark.parametrize("model", ["gpt-6.2-astra", "gpt-6.2-sol"])
def test_gpt62_service_tiers(model):
    with pytest.raises(InvokeBadRequestError, match="Flex"):
        responses.parameters(model, {"service_tier": "flex"}, None, None)
    with pytest.raises(InvokeBadRequestError, match="Ultrafast requires the Responses"):
        chat._chat_params(model, {"service_tier": "ultrafast"})
    assert (
        responses.parameters(model, {"service_tier": "ultrafast"}, None, None)[
            "service_tier"
        ]
        == "ultrafast"
    )


@pytest.mark.parametrize(
    "host", ["us.api.openai.com", "eu.api.openai.com", "gov.api.openai.com"]
)
def test_regional_usage_follows_the_configured_endpoint(host, monkeypatch):
    model = "gpt-6.2-astra"
    path = Path(__file__).resolve().parents[1] / "models/llm" / f"{model}.yaml"
    llm = OpenAILargeLanguageModel(
        [AIModelEntity.model_validate(yaml.safe_load(path.read_text()))]
    )
    response = {"usage": {"input_tokens": 1000, "output_tokens": 100}}
    monkeypatch.setenv("OPENAI_BASE_URL", f"https://{host}/v1")
    with llm.timing_context():
        regional = responses.usage(llm, model, {}, [], None, response, "", [])
        global_usage = responses.usage(
            llm,
            model,
            {"openai_api_base": "https://api.openai.com/v1"},
            [],
            None,
            response,
            "",
            [],
        )
        proxy = responses.usage(
            llm,
            model,
            {"openai_api_base": f"https://{host}.example/v1"},
            [],
            None,
            response,
            "",
            [],
        )
    assert regional.total_price == Decimal("0.0132")
    assert global_usage.total_price == proxy.total_price == Decimal("0.012")
