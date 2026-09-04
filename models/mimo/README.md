# Overview
Xiaomi MiMo provides advanced AI capabilities for chats and completions. This plugin enables developers to integrate Xiaomi MiMo's models, including the mimo-v2-flash model via the API.

# Configure
After installation, you need to get API keys from [Xiaomi MiMo](https://platform.xiaomimimo.com/#/console/api-keys).

## Request metadata

`Enable request metadata` is optional and disabled by default. Turning it on attaches `X-Dify-App-Id` and `X-Dify-Source` to each Xiaomi MiMo request as custom HTTP headers, so usage can be attributed to a specific Dify app. The opt-in is routed through the `extra_headers` credential because the underlying OAICompat base class merges it into the outbound request alongside the rest of the headers. The headers are forwarded by the underlying HTTP client and are used for observability / proxy-side propagation. Xiaomi MiMo does not document them. The Dify session lookup is best-effort: if the session context is not initialized, no headers are attached and the request is sent unchanged.