# Privacy

This plugin sends the configured Tokener.ai API key and language-model requests
directly to `https://api.tokener.ai`.
Requests may include model IDs, prompts, conversation messages, tool
definitions, and request metadata. Generated content, usage data, request IDs,
and errors are returned to Dify.

The plugin itself does not add persistent storage, analytics, or telemetry.
Tokener.ai may process and log request data, IP addresses, request IDs, and usage
metadata to provide, secure, and bill the service. Tokener.ai routes model
requests to upstream providers, currently including Anthropic and OpenAI. Their
applicable terms, retention rules, and privacy disclosures also govern that
processing.

Qwen-Long attachments include the original document bytes. Dify document URLs
are downloaded inside this plugin. Tokener.ai uploads the files to Alibaba Cloud
Model Studio for native parsing and requests deletion after inference.
The provider does not expire these files automatically. Failed deletion or
process termination can leave files until cleanup succeeds. If the last usable
provider credential disappears, an operator must remove the files manually.
See the [Model Studio file interface](https://help.aliyun.com/en/model-studio/openai-file-interface)
for storage and file processing behavior.

This document is the Tokener.ai privacy disclosure for the plugin. For upstream
processing, see the [Anthropic Privacy Policy](https://www.anthropic.com/legal/privacy)
and [OpenAI Privacy Policy](https://openai.com/policies/privacy-policy/).
Privacy questions can be sent to `privacy@tokener.ai`.
