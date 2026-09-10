# Overview

This plugin adds `deepseek-flash` (DeepSeek V4.1 Flash) alongside `deepseek-v4-flash`, `deepseek-v4-flash-vision-exp`, and `deepseek-v4-pro` through the official Chat Completions API.

Select **DeepSeek V4.1 Flash** for text and image input with reasoning, tool calling, and JSON Output.
It uses the same API key and base URL, with a 1M-token context and up to 393,216 output tokens, including reasoning.
The new V4.1 Flash entry defaults to thinking mode with `high` effort and a 65,536-token output limit.
Use the Thinking Mode switch to disable reasoning, or choose `low`, `high`, or `max` effort when it is enabled.
For the new V4.1 Flash entry, `top_p` applies only in thinking mode, from 0.95 to 1.0; `temperature` applies only in non-thinking mode.
See the [Chat Completions reference](https://api-docs.deepseek.com/api/create-chat-completion) and [Thinking Mode guide](https://api-docs.deepseek.com/guides/thinking_mode) for parameter behavior.

Images can be supplied as URLs or inline Base64 in user and tool messages.
Supported image formats are JPEG, PNG, GIF, and WebP; see the [official vision guide](https://api-docs.deepseek.com/guides/vision) for size and request limits.
Local token estimates exclude images; the API's returned token usage includes them.

Existing Dify apps can keep their selected model after upgrading; no model migration is required.
The `deepseek-v4-flash`, `deepseek-v4-flash-vision-exp`, and `deepseek-v4-pro` entries retain their existing IDs, labels, capabilities, parameter defaults, accepted ranges, and sampling behavior.
DeepSeek still accepts both legacy Flash API names and routes them to V4.1 Flash; this plugin sends the selected model ID unchanged.
Credential validation continues to use the existing `deepseek-v4-flash` API name.
Select **DeepSeek V4.1 Flash** when configuring the new model explicitly.
`deepseek-v4-pro` remains available; from September 14, 2026 at 04:00 UTC, DeepSeek will route its requests to V4.1 Flash until V4.1 Pro launches.
See the [official release notes](https://api-docs.deepseek.com/updates/#date-2026-09-10) for the migration schedule.

DeepSeek pricing varies by cache status and time window, so refer to the [official pricing page](https://api-docs.deepseek.com/quick_start/pricing) for current rates.

# Configure

Get an API key from [DeepSeek](https://platform.deepseek.com/api_keys), then configure it under Settings → Model Provider.

![DeepSeek configuration](_assets/deepseek.PNG)
