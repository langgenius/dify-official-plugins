"""Unit tests for provider.sagemaker.get_sagemaker_client.

The helper builds a fresh ``boto3.Session`` on every call so disk-refreshed
credentials (``aws sso login``, ``saml2aws login``, refreshed IMDS role) are
picked up by the next SageMaker invocation. The pre-fix code constructed
the client via ``boto3.client(...)`` (default session) and cached it on the
model instance, which left stale credentials in flight until the plugin
process was restarted.
"""

import importlib.util
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import MagicMock, patch

_PROVIDER_PATH = Path(__file__).resolve().parent.parent / "provider" / "sagemaker.py"
_spec = importlib.util.spec_from_file_location("sagemaker_provider", _PROVIDER_PATH)
sagemaker_provider = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sagemaker_provider)


def _credentials(
    *,
    access_key: str | None = None,
    secret_key: str | None = None,
    region: str | None = "us-east-1",
) -> Mapping[str, str]:
    creds: dict[str, str] = {}
    if access_key is not None:
        creds["aws_access_key_id"] = access_key
    if secret_key is not None:
        creds["aws_secret_access_key"] = secret_key
    if region is not None:
        creds["aws_region"] = region
    return creds


class TestExplicitKeys:
    def test_passes_access_key_and_secret_to_session(self) -> None:
        with patch.object(
            sagemaker_provider.boto3, "Session", return_value=MagicMock()
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.client = MagicMock(return_value=MagicMock())

            sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime",
                _credentials(
                    access_key="AKIA-TEST", secret_key="secret-test", region="us-west-2"
                ),
            )

        mock_session_cls.assert_called_once_with(
            aws_access_key_id="AKIA-TEST",
            aws_secret_access_key="secret-test",
            region_name="us-west-2",
        )
        mock_session.client.assert_called_once_with("sagemaker-runtime")

    def test_session_uses_requested_service(self) -> None:
        with patch.object(
            sagemaker_provider.boto3, "Session", return_value=MagicMock()
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.client = MagicMock(return_value=MagicMock())

            sagemaker_provider.get_sagemaker_client("s3", _credentials())

        mock_session.client.assert_called_once_with("s3")


class TestCredentialChain:
    """When no explicit keys are provided, the helper falls back to the
    default credential chain (``aws sso``, ``saml2aws``, IMDS). It must
    still build a fresh ``boto3.Session`` so refreshed credentials are
    picked up.
    """

    def test_uses_session_without_explicit_keys(self) -> None:
        with patch.object(
            sagemaker_provider.boto3, "Session", return_value=MagicMock()
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.client = MagicMock(return_value=MagicMock())

            sagemaker_provider.get_sagemaker_client("sagemaker-runtime", _credentials())

        mock_session_cls.assert_called_once_with(region_name="us-east-1")
        mock_session.client.assert_called_once_with("sagemaker-runtime")

    def test_uses_session_without_region(self) -> None:
        with patch.object(
            sagemaker_provider.boto3, "Session", return_value=MagicMock()
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.client = MagicMock(return_value=MagicMock())

            sagemaker_provider.get_sagemaker_client(
                "comprehend", _credentials(region=None)
            )

        mock_session_cls.assert_called_once_with(region_name=None)
        mock_session.client.assert_called_once_with("comprehend")


class TestBypassesDefaultSession:
    """The pre-fix code went through ``boto3.client(...)``, which uses
    boto3's default session. The default session caches credentials
    in-process, which is exactly the bug. The helper must NOT use the
    default session.
    """

    def test_does_not_use_default_boto3_client(self) -> None:
        with (
            patch.object(
                sagemaker_provider.boto3, "client", return_value=MagicMock()
            ) as mock_default_client,
            patch.object(
                sagemaker_provider.boto3, "Session", return_value=MagicMock()
            ) as mock_session_cls,
        ):
            mock_session = mock_session_cls.return_value
            mock_session.client = MagicMock(return_value=MagicMock())

            sagemaker_provider.get_sagemaker_client("sagemaker-runtime", _credentials())

        mock_default_client.assert_not_called()
        mock_session_cls.assert_called_once()


class TestPerCallSession:
    """The whole point of the fix: each call must build a fresh session
    so a credential refresh takes effect on the next invocation.
    """

    def test_two_consecutive_calls_make_two_sessions(self) -> None:
        with patch.object(
            sagemaker_provider.boto3, "Session", return_value=MagicMock()
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.client = MagicMock(return_value=MagicMock())

            sagemaker_provider.get_sagemaker_client("sagemaker-runtime", _credentials())
            sagemaker_provider.get_sagemaker_client("sagemaker-runtime", _credentials())

        assert mock_session_cls.call_count == 2

    def test_two_consecutive_calls_with_different_regions(self) -> None:
        with patch.object(
            sagemaker_provider.boto3, "Session", return_value=MagicMock()
        ) as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.client = MagicMock(return_value=MagicMock())

            sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime", _credentials(region="us-east-1")
            )
            sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime", _credentials(region="eu-west-1")
            )

        assert mock_session_cls.call_count == 2
        # Second call should pass the new region.
        second_call_kwargs = mock_session_cls.call_args_list[1].kwargs
        assert second_call_kwargs["region_name"] == "eu-west-1"
