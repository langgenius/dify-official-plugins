# Sarvam

Official Sarvam AI Token Factory models for Dify. The plugin uses the
OpenAI-compatible Chat Completions API at `https://api.sarvam.ai/v2` and sends
`User-Agent: dify-sarvam-plugin/<version>` on every request.

## Models

| Model | Context | Vision | Reasoning | Input / output per 1M |
| --- | ---: | --- | --- | --- |
| `sarvam-105b` | 128,000 | no | `none`, `low`, `medium`, `high` (default `low`) | $0.1596 / $0.6383 |
| `sarvam-105b-conversations` | 32,000 | no | off | $0.1596 / $0.6383 |
| `glm5.3` | 1,048,576 | no | `low`, `high`, `max` (default `max`) | $1.3404 / $4.1489 |
| `glm5.3-flash` | 1,048,576 | yes | `low`, `high`, `max` (default `high`) | $0.1436 / $0.4787 |
| `gemma4` | 262,144 | yes | `none`, `low`, `high`, `max` (default `none`) | $0.3723 / $0.9574 |
| `deepseekv4.1-flash-1017` | 1,048,576 | yes | `none`, `low`, `high`, `max` (default `high`) | $0.1489 / $0.5851 |
| `deepseekv4.1-flash-1017-interactive` | 1,048,576 | yes | `none`, `low`, `high`, `max` (default `high`) | $0.2660 / $1.1170 |

All models support streaming, tool calling, parallel tool calls, and structured
output. Reasoning models return `reasoning_content`, which the plugin displays
as a `<think>` block.

## Configure

1. Create an API key at [Sarvam key management](https://indus.sarvam.ai/key-management).
2. In Dify, open Settings, then Model Provider, then Sarvam.
3. Paste the API key. The default base URL is `https://api.sarvam.ai/v2`.
4. Save. The provider validates the key with `sarvam-105b`.

## Pricing

Prices are USD per 1M tokens at ₹94 per USD. `sarvam-105b` uses the list rate of
₹15 input, ₹5 cached input, and ₹60 output per 1M tokens. Sarvam's introductory
rate through the end of 2026 is lower, so Dify's cost display will overestimate
during that period.

Dify has no cached-input price field. Cached input is billed by Sarvam at a lower
rate, but Dify's estimate uses the full input price.

## Limits

- `sarvam-105b` output is plan-capped at 4,096 tokens on Starter, 16,384 on Pro,
  and 128,000 on Business. The plugin defaults to 4,096 so the default works on
  every plan.
- Images must be inline base64 data URIs. Sarvam rejects remote `http(s)` image
  URLs.
- `n` must be `1`. Dify does not send `n` by default.
- `stop` is capped at 4 sequences on `sarvam-105b`, `glm5.3`, and `gemma4`.
- Provisioned Throughput models and `sarvam-prism` are not included. They need
  organisation-level access or a different model type.

## Links

- [Sarvam Token Factory documentation](https://docs.sarvam.ai/api/token-factory/chat-completions)
- [Sarvam pricing](https://www.sarvam.ai/token-factory/pricing)
- [Plugin source](https://github.com/langgenius/dify-official-plugins/tree/main/models/sarvam)
