SILICONFLOW_CN_BASE_URL = "https://api.siliconflow.cn"
SILICONFLOW_INTERNATIONAL_BASE_URL = "https://api.siliconflow.com"


def get_base_url(credentials: dict) -> str:
    """API base for the configured endpoint. Defaults to the .cn endpoint so
    existing installations keep their exact current behavior; the international
    endpoint (api.siliconflow.com) uses separate accounts and keys."""
    if credentials.get("use_international_endpoint", "false") == "true":
        return SILICONFLOW_INTERNATIONAL_BASE_URL
    return SILICONFLOW_CN_BASE_URL
