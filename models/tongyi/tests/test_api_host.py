import pytest

from models._common import (
    DEFAULT_HTTP_BASE_ADDRESS,
    DEFAULT_WS_BASE_ADDRESS,
    INTL_HTTP_BASE_ADDRESS,
    INTL_WS_BASE_ADDRESS,
    get_api_host,
    get_compatible_base_url,
    get_http_base_address,
    get_ws_base_address,
    has_custom_api_host,
    normalize_api_host,
)

WORKSPACE_HOST = "llm-abc123.cn-beijing.maas.aliyuncs.com"


@pytest.mark.parametrize(
    "raw",
    [
        WORKSPACE_HOST,
        f"  {WORKSPACE_HOST}  ",
        f"https://{WORKSPACE_HOST}",
        f"http://{WORKSPACE_HOST}",
        f"https://{WORKSPACE_HOST}/",
        f"https://{WORKSPACE_HOST}/api/v1",
        f"https://{WORKSPACE_HOST}/api/v1/",
        f"https://{WORKSPACE_HOST}/compatible-mode/v1",
        f"wss://{WORKSPACE_HOST}/api-ws/v1/inference",
        f"{WORKSPACE_HOST}/api/v1",
    ],
)
def test_normalize_api_host_reduces_pasted_urls_to_a_bare_host(raw: str) -> None:
    assert normalize_api_host(raw) == WORKSPACE_HOST


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_normalize_api_host_treats_blank_input_as_unset(raw: str | None) -> None:
    assert normalize_api_host(raw) == ""


def test_normalize_api_host_keeps_an_explicit_port() -> None:
    assert normalize_api_host("https://gateway.internal:8443/api/v1") == "gateway.internal:8443"


def test_api_host_defaults_to_the_shared_domestic_host() -> None:
    credentials = {"dashscope_api_key": "test-key"}

    assert get_api_host(credentials) == "dashscope.aliyuncs.com"
    assert get_http_base_address(credentials) == DEFAULT_HTTP_BASE_ADDRESS
    assert get_ws_base_address(credentials) == DEFAULT_WS_BASE_ADDRESS
    assert not has_custom_api_host(credentials)


def test_api_host_falls_back_to_the_shared_international_host() -> None:
    credentials = {"dashscope_api_key": "test-key", "use_international_endpoint": "true"}

    assert get_api_host(credentials) == "dashscope-intl.aliyuncs.com"
    assert get_http_base_address(credentials) == INTL_HTTP_BASE_ADDRESS
    assert get_ws_base_address(credentials) == INTL_WS_BASE_ADDRESS
    assert not has_custom_api_host(credentials)


def test_api_host_derives_every_base_address_from_a_workspace_host() -> None:
    credentials = {"dashscope_api_key": "test-key", "api_host": WORKSPACE_HOST}

    assert get_http_base_address(credentials) == f"https://{WORKSPACE_HOST}/api/v1"
    assert get_ws_base_address(credentials) == f"wss://{WORKSPACE_HOST}/api-ws/v1/inference"
    assert get_compatible_base_url(credentials) == f"https://{WORKSPACE_HOST}/compatible-mode/v1"
    assert has_custom_api_host(credentials)


def test_api_host_overrides_the_international_endpoint_toggle() -> None:
    credentials = {
        "dashscope_api_key": "test-key",
        "api_host": f"https://{WORKSPACE_HOST}/api/v1",
        "use_international_endpoint": "true",
    }

    assert get_api_host(credentials) == WORKSPACE_HOST
    assert get_http_base_address(credentials) == f"https://{WORKSPACE_HOST}/api/v1"


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_api_host_keeps_the_toggle_in_charge(blank: str) -> None:
    credentials = {
        "dashscope_api_key": "test-key",
        "api_host": blank,
        "use_international_endpoint": "true",
    }

    assert get_http_base_address(credentials) == INTL_HTTP_BASE_ADDRESS
    assert not has_custom_api_host(credentials)


def test_trial_and_regional_hosts_are_passed_through_unchanged() -> None:
    for host in (
        "trial.cn-beijing.maas.aliyuncs.com",
        "llm-xyz.eu-central-1.maas.aliyuncs.com",
        "cn-hongkong.dashscope.aliyuncs.com",
    ):
        assert get_api_host({"api_host": host}) == host
