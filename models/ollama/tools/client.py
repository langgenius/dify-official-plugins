from typing import Any

import requests

OLLAMA_CLOUD_API_BASE = "https://ollama.com/api"


def call_ollama_cloud_api(
    credentials: dict[str, Any],
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    api_key = credentials.get("ollama_api_key")
    if not api_key:
        raise ValueError("Ollama API key is missing.")

    response = requests.post(
        f"{OLLAMA_CLOUD_API_BASE}/{path.lstrip('/')}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=(10, 60),
    )
    response.raise_for_status()
    return response.json()
