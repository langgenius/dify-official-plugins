# Privacy

This plugin sends requests only to the LiteLLM Proxy URL that you enter in the
model settings. The plugin has no default remote endpoint and no server of its own.

Each request can include the model name, prompts, conversation messages, tool
definitions, texts to embed, and request parameters. If you set an API key, the
plugin sends it as a `Bearer` token in the `Authorization` header. Responses,
token usage, and errors go back to Dify.

The plugin does not add persistent storage, analytics, or telemetry.

The operator of the LiteLLM Proxy controls what happens to the data after it
arrives. A proxy can log requests, track spend, and forward each request to the
upstream model provider that you configured. Their terms and privacy policies
apply to that processing. See the
[LiteLLM Proxy documentation](https://docs.litellm.ai/docs/proxy/quick_start)
for the logging options of the proxy.
