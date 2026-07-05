# Privacy

This plugin forwards chat-completion requests from Dify to the AI/ML API
endpoint configured by the operator (`https://api.aimlapi.com/v1` by
default). The plugin does not collect, log, or transmit user data outside
of that request flow.

- The plugin does not phone home, send telemetry, or read environment
  variables other than the API key and endpoint URL supplied by the
  operator.
- All prompts and completions are passed through to AI/ML API in the same
  form Dify delivers them; no transformation or redaction is applied.
- AI/ML API's own privacy and data-retention practices apply to the
  upstream requests — see [https://aimlapi.com/](https://aimlapi.com/) for
  details.

Dify users retain ownership of all content passed through the plugin.