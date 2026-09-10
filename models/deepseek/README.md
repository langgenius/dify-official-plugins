# Overview

This plugin integrates `deepseek-flash` (DeepSeek V4.1 Flash) and `deepseek-v4-pro` through the official Chat Completions API.

Select **DeepSeek V4.1 Flash** for text and image input with reasoning, tool calling, and JSON Output.
It uses the same API key and base URL, with a 1M-token context and up to 393,216 output tokens, including reasoning.
The plugin defaults to thinking mode with `high` effort and a 65,536-token output limit.
Use the Thinking Mode switch to disable reasoning, or choose `low`, `high`, or `max` effort when it is enabled.
`top_p` applies only in thinking mode, from 0.95 to 1.0; `temperature` applies only in non-thinking mode.
See the [Chat Completions reference](https://api-docs.deepseek.com/api/create-chat-completion) and [Thinking Mode guide](https://api-docs.deepseek.com/guides/thinking_mode) for parameter behavior.

Images can be supplied as URLs or inline Base64 in user and tool messages.
Supported image formats are JPEG, PNG, GIF, and WebP; see the [official vision guide](https://api-docs.deepseek.com/guides/vision) for size and request limits.
Local token estimates exclude images; the API's returned token usage includes them.

The retired `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` entries have been replaced by `deepseek-flash`.
Update existing Dify apps to select **DeepSeek V4.1 Flash** after upgrading this plugin.
DeepSeek temporarily routes the old API names to V4.1 Flash, but they are no longer offered by this plugin.
`deepseek-v4-pro` remains available; from September 14, 2026 at 04:00 UTC, DeepSeek will route its requests to V4.1 Flash until V4.1 Pro launches.
See the [official release notes](https://api-docs.deepseek.com/updates/#date-2026-09-10) for the migration schedule.

DeepSeek pricing varies by cache status and time window, so refer to the [official pricing page](https://api-docs.deepseek.com/quick_start/pricing) for current rates.

# Configure

Get an API key from [DeepSeek](https://platform.deepseek.com/api_keys), then configure it under Settings → Model Provider.

![DeepSeek configuration](_assets/deepseek.PNG)
