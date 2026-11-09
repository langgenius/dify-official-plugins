import math


def request_options(parameters: dict) -> dict:
    """Omit unset controls to preserve the OpenAI SDK defaults."""
    options = {}
    value = parameters.get("max_retries")
    if value not in (None, ""):
        try:
            retries = int(value)
            if isinstance(value, bool) or retries < 0 or retries != float(value):
                raise ValueError
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("max_retries must be a non-negative integer") from error
        options["max_retries"] = retries

    value = parameters.get("request_timeout")
    if value not in (None, ""):
        try:
            timeout = float(value)
            if isinstance(value, bool) or not math.isfinite(timeout) or timeout <= 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("request_timeout must be positive finite seconds") from error
        options["timeout"] = timeout
    return options


def normalize_openai_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None

    cleaned = str(base_url).strip().rstrip("/")
    if not cleaned:
        return None

    if cleaned.endswith("/v1"):
        return cleaned

    return f"{cleaned}/v1"
