import os
from pathlib import Path

import pytest
import yaml

from dify_plugin.config.integration_config import IntegrationConfig
from dify_plugin.core.entities.plugin.request import (
    ModelActions,
    ModelInvokeLLMRequest,
    PluginInvokeType,
)
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.integration.run import PluginRunner


def get_all_models() -> list[str]:
    models_dir = Path(__file__).parent.parent / "models" / "llm"
    position_file = models_dir / "_position.yaml"
    data = yaml.safe_load(position_file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected list in {position_file}")
    return [str(x).strip() for x in data if str(x).strip()]


def _plugin_path() -> str:
    plugin_path = os.getenv("PLUGIN_FILE_PATH")
    if not plugin_path:
        plugin_path = str(Path(__file__).parent.parent)
    return plugin_path


@pytest.fixture(scope="session")
def runner() -> PluginRunner:
    """Start plugin only once for the whole test session.

    Notes:
    - In CI, the first start can be slow because the daemon needs to resolve/install deps.
      PluginRunner has a hard 30s ready timeout; a retry is often enough after deps are cached.
    """
    cfg = IntegrationConfig()
    plugin_path = _plugin_path()

    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            r = PluginRunner(config=cfg, plugin_package_path=plugin_path, extra_args=["--enable-logs"])
            r.__enter__()
            return r
        except TimeoutError as e:
            last_err = e
            # Backoff a bit; the previous attempt may have partially finished installing deps.
            import time

            time.sleep(5 * attempt)
            continue

    raise TimeoutError(f"Plugin failed to start after retries: {last_err}")


@pytest.fixture(scope="session", autouse=True)
def _close_runner(request: pytest.FixtureRequest, runner: PluginRunner):
    def fin():
        try:
            runner.__exit__(None, None, None)
        except Exception:
            pass

    request.addfinalizer(fin)


@pytest.mark.parametrize("model_name", get_all_models())
def test_llm_invoke(model_name: str, runner: PluginRunner) -> None:
    api_key = os.getenv("VOLCENGINE_API_KEY")
    if not api_key:
        raise ValueError("VOLCENGINE_API_KEY environment variable is required")

    payload = ModelInvokeLLMRequest(
        user_id="test_user",
        provider="volcengine",
        model_type=ModelType.LLM,
        model=model_name,
        credentials={
            "ark_api_key": api_key,
            "api_endpoint_host": os.getenv(
                "VOLCENGINE_API_ENDPOINT", "https://ark.cn-beijing.volces.com/api/v3"
            ),
        },
        prompt_messages=[{"role": "user", "content": "Say hello in one word."}],
        model_parameters={"max_tokens": 32},
        stop=None,
        tools=None,
        stream=True,
    )

    results: list[LLMResultChunk] = []
    for result in runner.invoke(
        access_type=PluginInvokeType.Model,
        access_action=ModelActions.InvokeLLM,
        payload=payload,
        response_type=LLMResultChunk,
    ):
        results.append(result)

    assert len(results) > 0, f"No results received for model {model_name}"
    full_content = "".join(r.delta.message.content for r in results if r.delta.message.content)
    assert len(full_content) > 0, f"Empty content for model {model_name}"
