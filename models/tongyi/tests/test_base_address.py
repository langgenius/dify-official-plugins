import sys
from pathlib import Path

import pytest
import yaml

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from dify_plugin.errors.model import InvokeBadRequestError

from models._common import (  # noqa: E402
    DEFAULT_COMPATIBLE_BASE_URL,
    DEFAULT_HTTP_BASE_ADDRESS,
    DEFAULT_WS_BASE_ADDRESS,
    INTL_COMPATIBLE_BASE_URL,
    INTL_HTTP_BASE_ADDRESS,
    INTL_WS_BASE_ADDRESS,
    get_http_base_address,
    get_openai_compatible_base_url,
    get_ws_base_address,
)

WORKSPACE_NATIVE = "https://ws-example.cn-beijing.maas.aliyuncs.com/api/v1"
WORKSPACE_COMPATIBLE = (
    "https://ws-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
)
WORKSPACE_ORIGIN = "https://ws-example.cn-beijing.maas.aliyuncs.com"
WORKSPACE_WS = "wss://ws-example.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"


def _provider_variables() -> list[str]:
    schema = yaml.safe_load(
        (_PLUGIN_DIR / "provider" / "tongyi.yaml").read_text(encoding="utf-8")
    )
    return [
        field["variable"]
        for field in schema["provider_credential_schema"]["credential_form_schemas"]
    ]


def test_provider_schema_exposes_optional_dashscope_api_base() -> None:
    assert "dashscope_api_base" in _provider_variables()


def test_default_china_endpoint() -> None:
    credentials = {"dashscope_api_key": "k"}
    assert get_http_base_address(credentials) == DEFAULT_HTTP_BASE_ADDRESS
    assert get_ws_base_address(credentials) == DEFAULT_WS_BASE_ADDRESS
    assert get_openai_compatible_base_url(credentials) == DEFAULT_COMPATIBLE_BASE_URL


def test_international_endpoint() -> None:
    credentials = {
        "dashscope_api_key": "k",
        "use_international_endpoint": "true",
    }
    assert get_http_base_address(credentials) == INTL_HTTP_BASE_ADDRESS
    assert get_ws_base_address(credentials) == INTL_WS_BASE_ADDRESS
    assert get_openai_compatible_base_url(credentials) == INTL_COMPATIBLE_BASE_URL


def test_blank_custom_base_keeps_default() -> None:
    credentials = {"dashscope_api_key": "k", "dashscope_api_base": "   "}
    assert get_http_base_address(credentials) == DEFAULT_HTTP_BASE_ADDRESS


def test_workspace_native_base_overrides_international_flag() -> None:
    credentials = {
        "dashscope_api_key": "k",
        "use_international_endpoint": "true",
        "dashscope_api_base": f"  {WORKSPACE_NATIVE}  ",
    }
    assert get_http_base_address(credentials) == WORKSPACE_NATIVE
    assert get_ws_base_address(credentials) == WORKSPACE_WS
    assert get_openai_compatible_base_url(credentials) == WORKSPACE_COMPATIBLE


def test_workspace_compatible_url_converts_for_dashscope_sdk() -> None:
    credentials = {"dashscope_api_base": WORKSPACE_COMPATIBLE}
    assert get_http_base_address(credentials) == WORKSPACE_NATIVE
    assert get_openai_compatible_base_url(credentials) == WORKSPACE_COMPATIBLE


def test_workspace_origin_appends_api_v1() -> None:
    credentials = {"dashscope_api_base": WORKSPACE_ORIGIN}
    assert get_http_base_address(credentials) == WORKSPACE_NATIVE
    assert get_openai_compatible_base_url(credentials) == WORKSPACE_COMPATIBLE


@pytest.mark.parametrize(
    "invalid",
    [
        "not-a-url",
        "ftp://dashscope.aliyuncs.com/api/v1",
        "https://",
        "ws-example.cn-beijing.maas.aliyuncs.com/api/v1",
    ],
)
def test_invalid_custom_base_raises(invalid: str) -> None:
    with pytest.raises(InvokeBadRequestError, match="DashScope API Base URL"):
        get_http_base_address({"dashscope_api_base": invalid})
