from replicate.exceptions import ModelError, ReplicateError
from dify_plugin.errors.model import InvokeBadRequestError, InvokeError

from models.llm._metadata import apply_dify_metadata_if_enabled


class _CommonReplicate:
    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {InvokeBadRequestError: [ReplicateError, ModelError]}

    @staticmethod
    def _build_replicate_client(credentials: dict):
        """Construct a ``ReplicateClient`` with the opt-in Dify headers attached.

        Runs the opt-in ``apply_dify_metadata_if_enabled(credentials)`` helper so
        any caller-supplied ``extra_headers`` (or the Dify default headers when
        ``enable_request_metadata`` is ``"enabled"``) are written into
        ``credentials['extra_headers']`` before we read it back to populate
        ``headers=`` on the underlying ``httpx.Client``. The Replicate SDK
        forwards every entry of ``httpx.Client.headers`` on each outbound
        request, which is the carrier for the Dify observability headers.

        This is a backwards-compatible extension: when the opt-in is disabled
        (the default), ``credentials['extra_headers']`` is unset and the
        client gets ``headers={}``, which ``httpx`` treats as a no-op.
        """
        from replicate import Client as ReplicateClient  # local import to avoid cycles

        apply_dify_metadata_if_enabled(credentials)
        return ReplicateClient(
            api_token=credentials["replicate_api_token"],
            timeout=30,
            headers=credentials.get("extra_headers", {}),
        )
