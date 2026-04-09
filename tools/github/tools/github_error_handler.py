"""
Common error handler for GitHub API responses
"""
from collections.abc import Generator
from typing import Any, Callable

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


def handle_github_api_error(response, context: str = ""):
    """
    Handle common GitHub API errors with user-friendly messages

    Args:
        response: The requests.Response object
        context: Additional context about the operation (e.g., "merge pull request")

    Raises:
        InvokeError: With appropriate error message
    """
    try:
        response_data = response.json()
        error_msg = response_data.get('message', 'Unknown error')
    except Exception:
        error_msg = 'Unknown error'

    status_code = response.status_code

    if status_code == 403:
        if 'forbids access via a personal access token (classic)' in error_msg:
            raise InvokeError(
                "Access denied: Please use a fine-grained personal access token instead of a classic token. "
                "Create one at https://github.com/settings/tokens?type=beta"
            )
        elif 'API rate limit exceeded' in error_msg:
            raise InvokeError(
                f"GitHub API rate limit exceeded. Please wait before trying again. {error_msg}"
            )
        else:
            raise InvokeError(
                f"Access denied: {error_msg}. "
                "You may need appropriate permissions to access this repository or perform this action."
            )

    elif status_code == 404:
        raise InvokeError(
            f"Resource not found: {error_msg}. Please check the repository name, owner, and resource identifier."
        )

    elif status_code == 422:
        # Validation failed
        errors = response_data.get('errors', []) if isinstance(response_data, dict) else []
        if errors:
            error_details = "; ".join([
                e.get('message', str(e)) if isinstance(e, dict) else str(e)
                for e in errors
            ])
            raise InvokeError(f"Validation failed: {error_details}")
        else:
            raise InvokeError(f"Validation failed: {error_msg}")

    elif status_code == 401:
        raise InvokeError(
            f"Authentication failed: {error_msg}. Please check your access token."
        )

    elif status_code == 405:
        raise InvokeError(
            f"Operation not allowed: {error_msg}. "
            "This may be because the resource is in a state that doesn't allow this operation."
        )

    elif status_code == 409:
        raise InvokeError(
            f"Conflict: {error_msg}. "
            "This typically occurs when there's a merge conflict or the resource state conflicts with the operation."
        )

    else:
        context_msg = f" while {context}" if context else ""
        raise InvokeError(f"Request failed{context_msg}: {status_code} {error_msg}")


def safe_invoke(func: Callable) -> Callable:
    """
    Decorator to safely handle InvokeError exceptions and return them as text messages

    Usage:
        @safe_invoke
        def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
            ...
    """
    def wrapper(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            yield from func(self, tool_parameters)
        except InvokeError as e:
            yield self.create_text_message(f"❌ {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"❌ Unexpected error: {str(e)}")

    return wrapper
