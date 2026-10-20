# Tokener.ai

## Overview

Tokener.ai model provider for Dify. The plugin calls chat completions, rerank, and text embeddings through a fixed Tokener.ai endpoint.

## Configure

1. Install **Tokener.ai** from the Dify Marketplace.
2. Create an API key in the [Tokener.ai Console](https://console.tokener.dev/keys).
3. Open **Settings → Model Provider → Tokener.ai** and enter the key.

The API endpoint is fixed to `https://api.tokener.dev/v1`. The plugin does not accept provider keys, LiteLLM keys, organization IDs, or custom endpoints.

## Usage

In a Dify Workflow or Chatflow, add an LLM node, select **Tokener.ai**, and choose an available model.

Provider, LLM, and embedding validation use authenticated `GET /v1/models`. Rerank model validation sends one small rerank request to check model access.

Select **Qwen3 Rerank** as a rerank model. The API key must have access to `qwen3-rerank`. The public model directory does not list restricted rerank models.

The plugin registers a text embedding adapter. No predefined embedding models are included because the verified catalog lists none. The adapter needs matching model definitions before embedding models appear in Dify. Embeddings keep the requested model ID and the default vector dimensions. The plugin does not truncate texts or switch models.

## Model parameters

Parameter rules come from the catalog generator and explicit model profiles. The SDK does not send parameters that the selected model does not declare. New model IDs receive no sampling or reasoning controls until their API contract is verified.

| Models | Temperature | Top P | Presence penalty | Frequency penalty | Seed | Reasoning effort | Thinking |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna | Not declared | Not declared | Not declared | Not declared | Integer | none, low, medium, high, xhigh | Not declared |
| deepseek-v4-flash, deepseek-v4-pro, glm-5.2, kimi-k3 | 0–2 | 0.01–1 | -2–2 | -2–2 | Integer | Not declared | Not declared |

Staging GPT requests return HTTP 400 for custom temperature and Top P, even with `reasoning_effort=none`. GPT models do not expose these controls. Dify built-in calls can still supply them. The SDK filters these undeclared parameters before HTTP and sends declared parameters. DeepSeek and GLM deployment policies remove thinking controls, so the plugin does not declare them. Kimi reasoning effort is not declared because its effect is unverified. Seed forwarding does not guarantee repeatable output.

Profiles use the API parameter policy and the LiteLLM 1.103.0-rc.1 contract. Staging requests confirm request acceptance for the tested models and values. They do not prove parameter effects or production deployment settings. Production parameter overrides and DeepSeek Flash inference remain unverified. Recheck these profiles when deployment policies change. Catalog revisions do not include parameter policies.

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
