from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from dify_plugin.entities.model.text_embedding import EmbeddingUsage

from models.text_embedding.text_embedding import VolcengineMaaSTextEmbeddingModel


class FakeArkClient:
    def __init__(self):
        self.calls = []

    def multimodal_embeddings(self, input):
        self.calls.append(input)
        index = len(self.calls)
        return SimpleNamespace(
            data=SimpleNamespace(embedding=[float(index)]),
            usage=SimpleNamespace(total_tokens=index),
        )


def make_usage(tokens: int) -> EmbeddingUsage:
    return EmbeddingUsage(
        tokens=tokens,
        total_tokens=tokens,
        unit_price=Decimal("0"),
        price_unit=Decimal("0"),
        total_price=Decimal("0"),
        currency="USD",
        latency=0,
    )


def test_multimodal_text_batch_invokes_one_request_per_text(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_MAAS_MULTIMODAL_TEXT_EMBEDDING_CONCURRENCY", "1")
    fake_client = FakeArkClient()
    model = VolcengineMaaSTextEmbeddingModel([])

    with (
        patch.object(model, "_is_multimodal_model", return_value=True),
        patch.object(model, "_calc_response_usage", return_value=make_usage(6)),
        patch(
            "models.text_embedding.text_embedding.ArkClientV3.from_credentials",
            return_value=fake_client,
        ),
    ):
        result = model._generate_v3(
            model="Doubao-embedding-vision",
            credentials={},
            texts=["first", "second", "third"],
        )

    assert result.embeddings == [[1.0], [2.0], [3.0]]
    assert len(fake_client.calls) == 3
    assert [len(call) for call in fake_client.calls] == [1, 1, 1]
    assert [call[0]["text"] for call in fake_client.calls] == [
        "first",
        "second",
        "third",
    ]
