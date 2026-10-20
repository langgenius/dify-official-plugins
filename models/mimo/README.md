# Overview
Xiaomi MiMo provides advanced AI capabilities for chats and completions. This plugin supports `mimo-v2.6-pro`, `mimo-v2.6-flash`, and `mimo-v2.6-pro-ultraspeed`, with text, image and video input, streaming, tool calls, JSON mode, and optional thinking. Each model has a 1M-token context window and supports up to 131,072 output tokens.

# Configure
After installation, you need to get API keys from [Xiaomi MiMo](https://platform.xiaomimimo.com/#/console/api-keys).

For Token Plan subscriptions, use a `tp-` API key and select the corresponding China, Singapore, or Europe endpoint. Provider credential validation uses `mimo-v2.6-flash`. UltraSpeed requires separate access from Xiaomi and is not included in the standard Token Plan model list.

## Model migration (0.0.12)

The predefined model list now uses the V2.6 family. Update existing apps and workflow nodes to use the replacement model names:

| Previous model | Replacement |
| --- | --- |
| `mimo-v2.5-pro` | `mimo-v2.6-pro` |
| `mimo-v2.5` | `mimo-v2.6-flash` |
| `mimo-v2-flash` | `mimo-v2.6-flash` |

Xiaomi will automatically route V2.5 requests to V2.6 from **October 14, 2026 at 18:00 (UTC+8)**. The V2.5 names stop working on **October 21, 2026 at 10:00 (UTC+8)**. `mimo-v2-flash` was retired on June 30, 2026. Updating the plugin does not rewrite saved app or workflow configurations.

The plugin keeps thinking disabled by default. When enabled, Xiaomi fixes `temperature` at 1.0 and `top_p` at 0.95. `max_completion_tokens` limits both reasoning and answer tokens, with a default and maximum of 131,072. Displayed token costs use official overseas pay-per-use USD rates for uncached input and output; Token Plan billing is managed separately by Xiaomi.

Sources: [model list](https://mimo.mi.com/docs/zh-CN/quick-start/summary/model), [retirement schedule](https://mimo.mi.com/docs/zh-CN/updates/deprecate), [Chat Completions API](https://mimo.mi.com/docs/zh-CN/api/chat/openai-api), [Pro pricing](https://mimo.mi.com/models/zh-CN/mimo-v2.6-pro), [Flash pricing](https://mimo.mi.com/models/zh-CN/mimo-v2.6-flash), [UltraSpeed pricing](https://mimo.mi.com/models/zh-CN/mimo-v2.6-pro-ultraspeed), and [Token Plan models](https://mimo.mi.com/docs/en-US/quick-start/faq/token-plan/Plans%26Pricing).

## Request metadata

`Enable request metadata` is optional and disabled by default. Turning it on attaches `X-Dify-App-Id` and `X-Dify-Source` to each Xiaomi MiMo request as custom HTTP headers, so usage can be attributed to a specific Dify app. The opt-in is routed through the `extra_headers` credential because the underlying OAICompat base class merges it into the outbound request alongside the rest of the headers. The headers are forwarded by the underlying HTTP client and are used for observability / proxy-side propagation. Xiaomi MiMo does not document them. The Dify session lookup is best-effort: if the session context is not initialized, no headers are attached and the request is sent unchanged.
