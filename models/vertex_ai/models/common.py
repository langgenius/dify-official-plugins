from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from google.api_core import exceptions as gc_exc


class CommonVertexAi:
    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map vendor/library exceptions to unified plugin errors.
        Keys: errors exposed to callers (InvokeError subclasses). Using InvokeError as a catch-all is safe.
        Values: exception classes raised by SDKs/clients that should be normalized.
        """
        return {
            InvokeConnectionError: [gc_exc.ServiceUnavailable],
            InvokeServerUnavailableError: [gc_exc.InternalServerError],
            InvokeRateLimitError: [gc_exc.ResourceExhausted],
            InvokeAuthorizationError: [gc_exc.PermissionDenied],
            InvokeBadRequestError: [
                gc_exc.InvalidArgument,
                gc_exc.PermissionDenied,
                gc_exc.NotFound,
            ],
        }
