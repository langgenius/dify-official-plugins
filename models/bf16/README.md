# bf16.ai Model Provider for Dify

Official Dify model provider plugin for [bf16.ai](https://bf16.ai), providing OpenAI-compatible inference across 1M-context uncensored open-weight models with strict zero data retention and pay-as-you-go pricing.

## Supported Models

| Model ID | Context | Max Output | Multimodal | Capabilities |
| --- | --- | --- | --- | --- |
| `zai-org/glm-5.3-uncensored` | 1M | 131,072 | Text | Tool calling, structured output, reasoning |
| `deepseek/deepseek-v4.1-flash-uncensored` | 1M | 130,000 | Text + Vision | Tool calling, structured output, reasoning |
| `deepseek/deepseek-v4.1-flash-uncensored-fast` | 1M | 130,000 | Text + Vision | Tool calling, structured output, reasoning |
| `zai-org/glm-5.3-flash-uncensored` | 1M | 131,072 | Text + Vision | Tool calling, structured output, reasoning |
| `moonshotai/kimi-k3.1-pro-uncensored` | 1M | 131,072 | Text + Vision | Tool calling, structured output, reasoning |

## Configuration

1. Create an API key in the [bf16.ai Developer Console](https://bf16.ai/dashboard/keys).
2. In Dify, go to **Settings -> Model Provider -> bf16.ai**.
3. Enter your `sk-bf16-v1-...` API key (and optionally override the API Base URL; defaults to `https://api.bf16.ai/v1`).

## Documentation

- API docs: https://bf16.ai/docs
- Live pricing & rate tiers: https://bf16.ai/pricing
