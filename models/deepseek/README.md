# Overview

This plugin integrates the official DeepSeek models `deepseek-v4-flash`, `deepseek-v4-pro`, and the experimental `deepseek-v4-flash-vision-exp`.

The stable `deepseek-v4-flash` and `deepseek-v4-pro` API IDs automatically use the latest model versions.

Select `deepseek-v4-flash-vision-exp` for text and image input with reasoning, tool calling, and JSON Output.
It uses the same API key and base URL as the text models, with a 1M-token context and up to 384K output tokens.
Images can be supplied as URLs or inline Base64 in user messages through Chat Completions.
Supported image formats are JPEG, PNG, GIF, and WebP; see the [official vision guide](https://api-docs.deepseek.com/guides/vision/) for size and request limits.
Local token estimates exclude images; the API's returned token usage includes them.

DeepSeek pricing varies by cache status and time window, so refer to the [official pricing page](https://api-docs.deepseek.com/quick_start/pricing/) for current rates.

# Configure

Get an API key from [DeepSeek](https://platform.deepseek.com/api_keys), then configure it under Settings → Model Provider.

![DeepSeek configuration](_assets/deepseek.PNG)
