# Privacy

This plugin sends the configured bf16.ai API key and language-model requests
directly to `https://api.bf16.ai/v1` (or the custom endpoint URL explicitly
configured by the user). Requests may include model IDs, prompts, conversation
messages, images (for vision-capable models), tool definitions, and inference
parameters. Generated completions, usage statistics, and errors are returned to
Dify.

The plugin itself adds no persistent storage, analytics, or third-party
telemetry. bf16.ai operates with zero data retention on prompts and completions
by default; only operational billing metadata (token counts, model ID, status)
is recorded for account metering.

For complete details, see the [bf16.ai Privacy Policy](https://bf16.ai/legal/privacy)
and [Data Processing Addendum](https://bf16.ai/legal/dpa). Privacy questions can
be sent to `hello@bf16.ai`.
