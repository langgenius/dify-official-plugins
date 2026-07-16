DEFAULT_ENDPOINT_URL = "https://openrouter.ai/api/v1"


def normalize_endpoint_url(credentials: dict) -> str:
    """Resolve and normalize the API endpoint URL from credentials.

    Strips leading/trailing whitespace and trailing slashes from the URL.
    Falls back to DEFAULT_ENDPOINT_URL when the value is missing or blank.
    """
    endpoint_url = (
        (credentials.get("endpoint_url") or DEFAULT_ENDPOINT_URL).strip().rstrip("/")
    )
    return endpoint_url or DEFAULT_ENDPOINT_URL
