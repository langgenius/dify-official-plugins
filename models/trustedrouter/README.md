# TrustedRouter

**Author:** langgenius
**Type:** Model Provider

## Overview

[TrustedRouter](https://trustedrouter.com) is an OpenAI-compatible LLM router with privacy-focused routing tiers. Prompts and outputs are not logged or trained on, and requests can be routed with zero data retention (`trustedrouter/zdr`) or end-to-end confidential inference (`trustedrouter/e2e`).

## Configuration

1. Get an API key from [trustedrouter.com/keys](https://trustedrouter.com/keys).
2. In Dify, go to **Settings → Model Provider → TrustedRouter** and enter the API key.
3. Pick a routing model:

| Model | Routing behavior |
| --- | --- |
| `trustedrouter/auto` | Best available model for each request |
| `trustedrouter/fast` | Fast, low-latency models |
| `trustedrouter/cheap` | Most cost-effective models |
| `trustedrouter/zdr` | Zero-data-retention tier |
| `trustedrouter/e2e` | End-to-end confidential inference tier |
| `trustedrouter/synth` | Multi-model synthesis |
| `trustedrouter/synth-code` | Multi-model synthesis tuned for code |

Additional models can be added via the customizable-model option using the full model id. See the [model catalog](https://trustedrouter.com/models).
