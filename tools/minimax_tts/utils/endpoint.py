MINIMAX_ENDPOINTS = {
    # Byte-identical default: the host this plugin has always called. It still
    # serves /v1/t2a_v2 but no longer appears in MiniMax's current docs, which
    # list only the china and international hosts below.
    "legacy": "https://api.minimax.chat",
    "china": "https://api.minimaxi.com",
    "international": "https://api.minimax.io",
}


def get_base_url(credentials: dict) -> str:
    """API base for the configured MiniMax endpoint. MiniMax runs separate
    account systems: keys work only on the platform where they were minted."""
    choice = credentials.get("api_endpoint") or "legacy"
    return MINIMAX_ENDPOINTS.get(choice, MINIMAX_ENDPOINTS["legacy"])
