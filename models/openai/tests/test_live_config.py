from __future__ import annotations

import os

import conftest

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


def test_live_credentials_never_reveal_values() -> None:
    credentials = _Credentials(
        openai_api_key="secret-key",
        openai_organization="secret-organization",
    )

    assert "secret" not in repr(credentials)
    assert "secret" not in str(credentials)
    assert set(credentials) == {"openai_api_key", "openai_organization"}
