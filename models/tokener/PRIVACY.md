# Privacy

This plugin sends the configured Tokener.ai API key and language-model requests
directly to `https://api.tokener.dev`.
Requests may include model IDs, prompts, conversation messages, tool
definitions, and request metadata. Generated content, usage data, request IDs,
and errors are returned to Dify.

The plugin itself does not add persistent storage, analytics, or telemetry.
Tokener.ai may process and log request data, IP addresses, request IDs, and usage
metadata to provide, secure, and bill the service. Tokener.ai routes model
requests to upstream providers, currently including Anthropic and OpenAI. Their
applicable terms, retention rules, and privacy disclosures also govern that
processing.

This document is the Tokener.ai privacy disclosure for the plugin. For upstream
processing, see the [Anthropic Privacy Policy](https://www.anthropic.com/legal/privacy)
and [OpenAI Privacy Policy](https://openai.com/policies/privacy-policy/).
Privacy questions can be sent to `privacy@tokener.dev`.
