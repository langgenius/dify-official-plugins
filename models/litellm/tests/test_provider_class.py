from pathlib import Path

from dify_plugin import ModelProvider
from dify_plugin.core.utils.class_loader import load_single_subclass_from_source

ROOT = Path(__file__).resolve().parent.parent


def test_provider_module_has_one_model_provider() -> None:
    # The plugin loader fails if the module holds more than one ModelProvider subclass.
    cls = load_single_subclass_from_source(
        module_name="provider.litellm",
        script_path=str(ROOT / "provider" / "litellm.py"),
        parent_type=ModelProvider,
    )
    assert cls.__name__ == "LiteLLMProvider"
