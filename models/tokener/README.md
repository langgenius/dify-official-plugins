# Tokener.ai

## Overview

Tokener.ai model provider for Dify. Calls OpenAI-compatible chat completions through a fixed Tokener.ai endpoint.

## Configure

1. Install **Tokener.ai** from the Dify Marketplace.
2. Create an API key in the [Tokener.ai Console](https://console.tokener.dev/keys).
3. Open **Settings → Model Provider → Tokener.ai** and enter the key.

The API endpoint is fixed to `https://api.tokener.dev/v1`. The plugin does not accept provider keys, LiteLLM keys, organization IDs, or custom endpoints.

## Usage

In a Dify Workflow or Chatflow, add an LLM node, select **Tokener.ai**, and choose an available model.

Credential and model-access validation uses authenticated `GET /v1/models`.

## Sync models

Model YAML is generated from the Tokener.ai public catalog:

```bash
uv run python scripts/sync_catalog.py
uv run python scripts/sync_catalog.py --check
```

Only LLM entries are generated.

## Support

Open an issue in [dify-official-plugins](https://github.com/langgenius/dify-official-plugins/issues) and include the Dify version, plugin version, model ID, and request ID. Never include API keys or prompt content.

## License

Apache License 2.0. See the repository [LICENSE](https://github.com/langgenius/dify-official-plugins/blob/main/LICENSE).
