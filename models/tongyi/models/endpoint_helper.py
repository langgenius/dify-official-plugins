"""
Utility functions for managing DashScope API endpoint configuration.

This module provides helper functions to get the correct base_address
based on credentials, allowing thread-safe API calls without modifying
global state.
"""
from typing import Optional


def get_base_address(credentials: dict) -> Optional[str]:
    """
    Get the base address for DashScope API based on credentials.

    This function returns the appropriate base_address parameter to pass to
    DashScope API calls, avoiding the need to modify global state.

    Args:
        credentials: Model credentials dictionary containing the
                    'use_international_endpoint' configuration

    Returns:
        str: The base address URL, or None for domestic endpoint

    Example:
        >>> base_address = get_base_address(credentials)
        >>> response = dashscope.TextEmbedding.call(
        ...     model='text-embedding-v3',
        ...     input='test',
        ...     api_key=credentials['dashscope_api_key'],
        ...     base_address=base_address
        ... )
    """
    if credentials.get("use_international_endpoint", "false") == "true":
        return "https://dashscope-intl.aliyuncs.com/api/v1"

    # Return None for domestic endpoint (uses default)
    return None

