def normalize_openai_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None

    cleaned = str(base_url).strip().rstrip("/")
    if not cleaned:
        return None

    if cleaned.endswith("/v1"):
        return cleaned

    return f"{cleaned}/v1"
