## Privacy

This plugin does not collect or store user data for itself.

- Prompts, tool calls, and model outputs are sent only to the two upstream endpoints configured
  for each route.
- Routing state (tier decisions per session) is kept in the plugin process memory. It holds a
  hash-derived session key and counters, not message content. It is lost when the plugin restarts.
- API keys are stored by Dify as secret credentials and sent only to the matching upstream.
