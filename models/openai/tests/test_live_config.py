from __future__ import annotations

import os

import conftest
import pytest

from tests.live.conftest import _Credentials


def test_live_environment_is_narrow_and_process_values_win(tmp_path, mocker) -> None:
    mocker.patch.object(conftest, "ROOT", tmp_path)
    mocker.patch.dict(os.environ, {"OPENAI_API_KEY": "from-process"}, clear=True)
    (tmp_path / ".env").write_text(
        "\n".join(
            (
                "OPENAI_API_KEY=from-file",
                'OPENAI_ORGANIZATION="org-test"',
                "INSTALL_METHOD=remote",
            )
        ),
        encoding="utf-8",
    )

    conftest._load_live_environment()

    assert os.environ["OPENAI_API_KEY"] == "from-process"
    assert os.environ["OPENAI_ORGANIZATION"] == "org-test"
    assert "INSTALL_METHOD" not in os.environ


def test_nonempty_dotenv_key_replaces_an_empty_process_value(tmp_path, mocker) -> None:
    mocker.patch.object(conftest, "ROOT", tmp_path)
    mocker.patch.dict(os.environ, {"OPENAI_API_KEY": "  "}, clear=True)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=from-file\n",
        encoding="utf-8",
    )

    conftest._load_live_environment()

    assert os.environ["OPENAI_API_KEY"] == "from-file"


@pytest.mark.parametrize(
    ("requested", "api_key", "should_skip"),
    [
        (False, "key", True),
        (True, None, True),
        (True, "", True),
        (True, "  ", True),
        (True, "key", False),
    ],
)
def test_live_collection_requires_opt_in_and_a_nonempty_key(
    requested, api_key, should_skip, mocker
) -> None:
    environment = {} if api_key is None else {"OPENAI_API_KEY": api_key}
    mocker.patch.dict(os.environ, environment, clear=True)
    config = mocker.Mock()
    config.getoption.return_value = requested
    item = mocker.Mock()
    item.path = conftest.LIVE_TESTS / "test_example.py"
    item.get_closest_marker.return_value = mocker.sentinel.live_marker

    conftest.pytest_collection_modifyitems(config, [item])

    assert item.add_marker.called is should_skip


def test_live_credentials_never_reveal_values() -> None:
    credentials = _Credentials(
        openai_api_key="secret-key",
        openai_organization="secret-organization",
    )

    assert "secret" not in repr(credentials)
    assert "secret" not in str(credentials)
    assert set(credentials) == {"openai_api_key", "openai_organization"}
