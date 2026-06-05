from yarl import URL


def normalize_openai_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None

    normalized = str(URL(str(base_url).rstrip("/")))
    if normalized.endswith("/v1"):
        return normalized

    return str(URL(normalized) / "v1")
