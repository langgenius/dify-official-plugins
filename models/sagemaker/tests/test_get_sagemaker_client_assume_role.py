"""Unit tests for the assume-role path of provider.sagemaker.get_sagemaker_client.

``assume_role_arn`` has been declared in ``provider/sagemaker.yaml`` for a long
time but ``get_sagemaker_client`` used to ignore it. These tests pin down the
semantics ported from aws-samples/dify-aws-tool#169:

* no ``assume_role_arn`` (absent / empty / blank) => byte-for-byte legacy
  behaviour and no STS call at all;
* with ``assume_role_arn`` => ``sts:AssumeRole`` is called from a source
  session built with the explicit access key / secret key when configured,
  ``DurationSeconds=3600``, an auditable ``RoleSessionName`` prefix, and
  ``RefreshableCredentials`` with ``method="sts-assume-role"``;
* the refresh callable re-assumes with the SAME explicit source identity
  snapshot, even after the caller's credentials mapping has been mutated.

Everything is mocked: ``boto3.Session``, ``RefreshableCredentials`` and
``botocore.session.get_session`` never reach the network.
"""

import contextlib
import functools
import importlib.util
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from botocore.exceptions import ClientError

_PROVIDER_PATH = Path(__file__).resolve().parent.parent / "provider" / "sagemaker.py"
_spec = importlib.util.spec_from_file_location(
    "sagemaker_provider_assume_role", _PROVIDER_PATH
)
sagemaker_provider = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sagemaker_provider)

# Obviously fake placeholders; none of these resemble a real AWS key id.
ACCESS_KEY = "test-access-key-id"
SECRET_KEY = "test-secret"
REGION = "us-west-2"
ROLE_ARN = "arn:aws:iam::123456789012:role/TestRole"

# STS constraint on RoleSessionName.
_ROLE_SESSION_NAME_RE = re.compile(r"^[\w+=,.@-]{2,64}$", re.ASCII)


def _credentials(
    *,
    access_key: str | None = None,
    secret_key: str | None = None,
    region: str | None = REGION,
    assume_role_arn: str | None = None,
) -> dict[str, str]:
    creds: dict[str, str] = {}
    if access_key is not None:
        creds["aws_access_key_id"] = access_key
    if secret_key is not None:
        creds["aws_secret_access_key"] = secret_key
    if region is not None:
        creds["aws_region"] = region
    if assume_role_arn is not None:
        creds["assume_role_arn"] = assume_role_arn
    return creds


def _fake_assume_role_response() -> dict:
    return {
        "Credentials": {
            "AccessKeyId": "assumed-access-key-id",
            "SecretAccessKey": "assumed-secret",
            "SessionToken": "assumed-session-token",
            "Expiration": datetime(2030, 1, 1, tzinfo=timezone.utc),
        }
    }


@contextlib.contextmanager
def _mocked_aws():
    """Patch every AWS touchpoint of the provider module.

    ``boto3.Session(...)`` returns one shared MagicMock whose ``.client(name)``
    hands out a distinct MagicMock per service name, so the STS client and the
    target-service client can be told apart. Nothing here talks to AWS.
    """
    with (
        patch.object(sagemaker_provider.boto3, "Session") as mock_session_cls,
        patch.object(sagemaker_provider, "RefreshableCredentials") as mock_refreshable,
        patch.object(sagemaker_provider, "get_session") as mock_get_session,
    ):
        clients: dict[str, MagicMock] = {}

        def _client(service_name: str, *args, **kwargs) -> MagicMock:
            return clients.setdefault(
                service_name, MagicMock(name=f"{service_name}-client")
            )

        mock_session_cls.return_value.client.side_effect = _client
        sts_client = _client("sts")
        sts_client.assume_role.return_value = _fake_assume_role_response()

        yield SimpleNamespace(
            session_cls=mock_session_cls,
            session=mock_session_cls.return_value,
            clients=clients,
            sts=sts_client,
            refreshable=mock_refreshable,
            get_session=mock_get_session,
        )


class TestBackwardCompatibility:
    """Without ``assume_role_arn`` the helper must behave byte-for-byte like
    before: same ``boto3.Session`` kwargs, no STS client, no ``assume_role``
    call, no ``RefreshableCredentials``.
    """

    @pytest.mark.parametrize(
        "assume_role_arn", [None, "", "   "], ids=["absent", "empty", "blank"]
    )
    @pytest.mark.parametrize(
        ("creds_kwargs", "expected_session_kwargs"),
        [
            pytest.param(
                dict(access_key=ACCESS_KEY, secret_key=SECRET_KEY, region=REGION),
                dict(
                    aws_access_key_id=ACCESS_KEY,
                    aws_secret_access_key=SECRET_KEY,
                    region_name=REGION,
                ),
                id="explicit-keys-and-region",
            ),
            pytest.param(
                dict(region=REGION), dict(region_name=REGION), id="region-only"
            ),
            pytest.param(dict(region=None), dict(region_name=None), id="default-chain"),
        ],
    )
    def test_legacy_paths_make_no_sts_call(
        self, creds_kwargs, expected_session_kwargs, assume_role_arn
    ) -> None:
        with _mocked_aws() as aws:
            client = sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime",
                _credentials(assume_role_arn=assume_role_arn, **creds_kwargs),
            )

        aws.session_cls.assert_called_once_with(**expected_session_kwargs)
        aws.session.client.assert_called_once_with("sagemaker-runtime")
        assert client is aws.clients["sagemaker-runtime"]
        assert call("sts") not in aws.session.client.call_args_list
        aws.sts.assume_role.assert_not_called()
        aws.refreshable.create_from_metadata.assert_not_called()
        aws.get_session.assert_not_called()

    def test_role_session_prefix_is_ignored_without_role(self) -> None:
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime",
                _credentials(region=REGION),
                role_session_prefix="dify-sagemaker-embedding",
            )

        aws.session_cls.assert_called_once_with(region_name=REGION)
        aws.sts.assume_role.assert_not_called()

    def test_positional_signature_unchanged(self) -> None:
        """Existing call sites pass (service_name, credentials) positionally."""
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client("s3", _credentials(region=REGION))

        aws.session.client.assert_called_once_with("s3")
        assert sagemaker_provider.get_sagemaker_client.__defaults__ == (
            sagemaker_provider.DEFAULT_ROLE_SESSION_PREFIX,
        )


class TestAssumeRoleWithExplicitKeys:
    """[P1 F2] The identity used to call ``sts:AssumeRole`` must be the explicit
    access key / secret key when both are configured.
    """

    def _creds(self) -> dict[str, str]:
        return _credentials(
            access_key=ACCESS_KEY,
            secret_key=SECRET_KEY,
            region=REGION,
            assume_role_arn=ROLE_ARN,
        )

    def test_sts_source_session_uses_explicit_keys(self) -> None:
        with _mocked_aws() as aws:
            client = sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime", self._creds()
            )

        # 1st Session: source-account identity, used ONLY to call sts:AssumeRole.
        # 2nd Session: wraps the botocore session carrying the assumed credentials.
        assert aws.session_cls.call_args_list == [
            call(
                region_name=REGION,
                aws_access_key_id=ACCESS_KEY,
                aws_secret_access_key=SECRET_KEY,
            ),
            call(botocore_session=aws.get_session.return_value, region_name=REGION),
        ]
        assert aws.session.client.call_args_list == [
            call("sts"),
            call("sagemaker-runtime"),
        ]
        assert client is aws.clients["sagemaker-runtime"]

    def test_assume_role_parameters(self) -> None:
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client("sagemaker-runtime", self._creds())

        aws.sts.assume_role.assert_called_once()
        params = aws.sts.assume_role.call_args.kwargs
        assert params["RoleArn"] == ROLE_ARN
        assert params["DurationSeconds"] == 3600
        assert params["RoleSessionName"].startswith("dify-sagemaker-")
        assert _ROLE_SESSION_NAME_RE.match(params["RoleSessionName"])

    def test_refreshable_credentials_wiring(self) -> None:
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client("sagemaker-runtime", self._creds())

        aws.refreshable.create_from_metadata.assert_called_once()
        kwargs = aws.refreshable.create_from_metadata.call_args.kwargs
        assert kwargs["method"] == "sts-assume-role"
        assert kwargs["metadata"] == {
            "access_key": "assumed-access-key-id",
            "secret_key": "assumed-secret",
            "token": "assumed-session-token",
            "expiry_time": "2030-01-01T00:00:00+00:00",
        }
        assert callable(kwargs["refresh_using"])
        # The assumed credentials are installed on the botocore session that
        # the returned client is built from.
        assert (
            aws.get_session.return_value._credentials
            is aws.refreshable.create_from_metadata.return_value
        )

    def test_surrounding_whitespace_in_role_arn_is_stripped(self) -> None:
        creds = self._creds()
        creds["assume_role_arn"] = f"  {ROLE_ARN}\n"
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client("sagemaker-runtime", creds)

        assert aws.sts.assume_role.call_args.kwargs["RoleArn"] == ROLE_ARN

    def test_other_services_are_assumed_too(self) -> None:
        """The helper is shared: tts (comprehend) and speech2text (s3) callers
        gain cross-account access through the same path."""
        for service in ("s3", "comprehend"):
            with _mocked_aws() as aws:
                client = sagemaker_provider.get_sagemaker_client(service, self._creds())

            aws.sts.assume_role.assert_called_once()
            assert aws.session.client.call_args_list == [call("sts"), call(service)]
            assert client is aws.clients[service]


class TestAssumeRoleWithCredentialChain:
    """Without explicit keys the STS call falls back to the runtime
    environment's default credential chain (region only / nothing)."""

    def test_region_only_source_session_has_no_keys(self) -> None:
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime",
                _credentials(region="us-east-1", assume_role_arn=ROLE_ARN),
            )

        assert aws.session_cls.call_args_list == [
            call(region_name="us-east-1"),
            call(
                botocore_session=aws.get_session.return_value, region_name="us-east-1"
            ),
        ]
        aws.sts.assume_role.assert_called_once()
        assert aws.sts.assume_role.call_args.kwargs["RoleArn"] == ROLE_ARN

    def test_no_region_and_no_keys_uses_default_chain(self) -> None:
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime", _credentials(region=None, assume_role_arn=ROLE_ARN)
            )

        assert aws.session_cls.call_args_list == [
            call(),
            call(botocore_session=aws.get_session.return_value, region_name=None),
        ]
        aws.sts.assume_role.assert_called_once()

    @pytest.mark.parametrize(
        "creds_kwargs",
        [dict(access_key=ACCESS_KEY), dict(secret_key=SECRET_KEY)],
        ids=["access-key-only", "secret-key-only"],
    )
    def test_partial_keys_fall_back_to_default_chain(self, creds_kwargs) -> None:
        """Same rule as the legacy path: both halves are required to use
        explicit keys."""
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime",
                _credentials(region=REGION, assume_role_arn=ROLE_ARN, **creds_kwargs),
            )

        assert aws.session_cls.call_args_list[0] == call(region_name=REGION)


class TestRefreshUsesImmutableSourceIdentity:
    """[P1 F2] regression: every automatic refresh must re-assume the role with
    the SAME explicit source identity that was configured when the client was
    built, not with whatever mutable state exists at refresh time.
    """

    @staticmethod
    def _build_and_capture_refresh(aws, credentials, **kwargs):
        sagemaker_provider.get_sagemaker_client(
            "sagemaker-runtime", credentials, **kwargs
        )
        return aws.refreshable.create_from_metadata.call_args.kwargs["refresh_using"]

    def test_refresh_reuses_explicit_keys(self) -> None:
        with _mocked_aws() as aws:
            refresh_using = self._build_and_capture_refresh(
                aws,
                _credentials(
                    access_key=ACCESS_KEY,
                    secret_key=SECRET_KEY,
                    region=REGION,
                    assume_role_arn=ROLE_ARN,
                ),
                role_session_prefix="dify-sagemaker-embedding",
            )
            aws.session_cls.reset_mock()
            aws.sts.assume_role.reset_mock()

            metadata = refresh_using()

        aws.session_cls.assert_called_once_with(
            region_name=REGION,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
        )
        aws.sts.assume_role.assert_called_once()
        params = aws.sts.assume_role.call_args.kwargs
        assert params["RoleArn"] == ROLE_ARN
        assert params["DurationSeconds"] == 3600
        assert params["RoleSessionName"].startswith("dify-sagemaker-embedding-")
        assert metadata["access_key"] == "assumed-access-key-id"
        assert metadata["expiry_time"] == "2030-01-01T00:00:00+00:00"

    def test_refresh_ignores_later_mutation_of_credentials_mapping(self) -> None:
        credentials = _credentials(
            access_key=ACCESS_KEY,
            secret_key=SECRET_KEY,
            region=REGION,
            assume_role_arn=ROLE_ARN,
        )
        with _mocked_aws() as aws:
            refresh_using = self._build_and_capture_refresh(aws, credentials)

            # Simulate another tenant's configuration being written into the
            # very same mapping after the client was built.
            credentials["aws_access_key_id"] = "other-tenant-access-key-id"
            credentials["aws_secret_access_key"] = "other-tenant-secret"
            credentials["aws_region"] = "eu-west-1"
            credentials["assume_role_arn"] = "arn:aws:iam::210987654321:role/OtherRole"
            aws.session_cls.reset_mock()
            aws.sts.assume_role.reset_mock()

            refresh_using()

        aws.session_cls.assert_called_once_with(
            region_name=REGION,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
        )
        assert aws.sts.assume_role.call_args.kwargs["RoleArn"] == ROLE_ARN

    def test_refresh_closure_is_a_partial_with_explicit_snapshot(self) -> None:
        with _mocked_aws() as aws:
            refresh_using = self._build_and_capture_refresh(
                aws,
                _credentials(
                    access_key=ACCESS_KEY,
                    secret_key=SECRET_KEY,
                    region=REGION,
                    assume_role_arn=ROLE_ARN,
                ),
                role_session_prefix="dify-sagemaker-rerank",
            )

        assert isinstance(refresh_using, functools.partial)
        assert refresh_using.func is sagemaker_provider._refresh_assume_role_credentials
        assert refresh_using.args == ()
        assert refresh_using.keywords == {
            "access_key": ACCESS_KEY,
            "secret_key": SECRET_KEY,
            "region": REGION,
            "role_arn": ROLE_ARN,
            "role_session_prefix": "dify-sagemaker-rerank",
        }

    def test_refresh_with_default_chain_keeps_no_keys(self) -> None:
        with _mocked_aws() as aws:
            refresh_using = self._build_and_capture_refresh(
                aws, _credentials(region=REGION, assume_role_arn=ROLE_ARN)
            )
            aws.session_cls.reset_mock()

            refresh_using()

        aws.session_cls.assert_called_once_with(region_name=REGION)


class TestRoleSessionName:
    @pytest.mark.parametrize(
        ("prefix_kwargs", "expected_prefix"),
        [
            pytest.param({}, "dify-sagemaker-", id="default"),
            pytest.param(
                {"role_session_prefix": "dify-sagemaker-embedding"},
                "dify-sagemaker-embedding-",
                id="embedding",
            ),
            pytest.param(
                {"role_session_prefix": "dify-sagemaker-rerank"},
                "dify-sagemaker-rerank-",
                id="rerank",
            ),
        ],
    )
    def test_prefix_reflects_caller(self, prefix_kwargs, expected_prefix) -> None:
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime",
                _credentials(assume_role_arn=ROLE_ARN),
                **prefix_kwargs,
            )

        name = aws.sts.assume_role.call_args.kwargs["RoleSessionName"]
        assert name.startswith(expected_prefix)
        assert name[len(expected_prefix) :].isdigit()
        assert _ROLE_SESSION_NAME_RE.match(name)

    def test_prefixes_are_distinct(self) -> None:
        seen: dict[str, str] = {}
        for prefix in (
            "dify-sagemaker",
            "dify-sagemaker-embedding",
            "dify-sagemaker-rerank",
        ):
            with _mocked_aws() as aws:
                sagemaker_provider.get_sagemaker_client(
                    "sagemaker-runtime",
                    _credentials(assume_role_arn=ROLE_ARN),
                    role_session_prefix=prefix,
                )
            name = aws.sts.assume_role.call_args.kwargs["RoleSessionName"]
            seen[prefix] = name.rsplit("-", 1)[0]

        assert seen == {
            "dify-sagemaker": "dify-sagemaker",
            "dify-sagemaker-embedding": "dify-sagemaker-embedding",
            "dify-sagemaker-rerank": "dify-sagemaker-rerank",
        }

    def test_build_role_session_name_format(self) -> None:
        with patch.object(sagemaker_provider.time, "time", return_value=1_700_000_000):
            assert (
                sagemaker_provider._build_role_session_name("dify-sagemaker-rerank")
                == "dify-sagemaker-rerank-1700000000"
            )

    def test_name_is_sanitised_and_truncated(self) -> None:
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime",
                _credentials(assume_role_arn=ROLE_ARN),
                role_session_prefix="bad prefix/with:chars!" + "x" * 100,
            )

        name = aws.sts.assume_role.call_args.kwargs["RoleSessionName"]
        assert _ROLE_SESSION_NAME_RE.match(name)
        assert len(name) <= 64
        assert name.startswith("bad-prefix-with-chars-xxx")
        assert name.rsplit("-", 1)[1].isdigit()

    def test_empty_prefix_falls_back_to_default(self) -> None:
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client(
                "sagemaker-runtime",
                _credentials(assume_role_arn=ROLE_ARN),
                role_session_prefix="",
            )

        name = aws.sts.assume_role.call_args.kwargs["RoleSessionName"]
        assert name.startswith("dify-sagemaker-")
        assert _ROLE_SESSION_NAME_RE.match(name)


class TestNoClientCache:
    """Deliberately no cache and no lock (unlike dify-aws-tool#169): every call
    builds a fresh session and assumes the role again, so there is no shared
    mutable state that could pair one tenant's client with another's config.
    """

    def test_each_call_assumes_role_again(self) -> None:
        creds = _credentials(
            access_key=ACCESS_KEY,
            secret_key=SECRET_KEY,
            region=REGION,
            assume_role_arn=ROLE_ARN,
        )
        with _mocked_aws() as aws:
            sagemaker_provider.get_sagemaker_client("sagemaker-runtime", creds)
            sagemaker_provider.get_sagemaker_client("sagemaker-runtime", creds)

        assert aws.sts.assume_role.call_count == 2
        assert aws.refreshable.create_from_metadata.call_count == 2
        assert aws.get_session.call_count == 2
        # Two source sessions + two assumed-role sessions.
        assert aws.session_cls.call_count == 4

    def test_module_has_no_client_cache_state(self) -> None:
        assert not hasattr(sagemaker_provider, "_client_lock")
        assert "threading" not in vars(sagemaker_provider)
        public_names = [n for n in vars(sagemaker_provider) if not n.startswith("__")]
        assert not any(
            "cache" in name.lower() for name in public_names
        ), "get_sagemaker_client must stay fresh-per-call (PR #3561)"


class TestErrorPropagation:
    """No custom exception hierarchy in the helper: an STS failure propagates
    as the original botocore ``ClientError`` and no client is handed out."""

    def test_sts_client_error_propagates_unchanged(self) -> None:
        error = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "not allowed"}}, "AssumeRole"
        )
        with _mocked_aws() as aws:
            aws.sts.assume_role.side_effect = error

            with pytest.raises(ClientError) as excinfo:
                sagemaker_provider.get_sagemaker_client(
                    "sagemaker-runtime",
                    _credentials(
                        access_key=ACCESS_KEY,
                        secret_key=SECRET_KEY,
                        region=REGION,
                        assume_role_arn=ROLE_ARN,
                    ),
                )

        assert excinfo.value is error
        aws.refreshable.create_from_metadata.assert_not_called()
        assert call("sagemaker-runtime") not in aws.session.client.call_args_list
