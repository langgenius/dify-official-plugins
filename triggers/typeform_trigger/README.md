# Typeform Trigger Plugin

Dify trigger plugin that listens for Typeform `form_response` webhooks. Each submission is forwarded to your workflow with the full response payload so you can automate follow-up actions in real time.


## Configure the Typeform Webhook

1. Open your Typeform form → **Connect** → **Webhooks**.
2. Add a new webhook using the Dify endpoint (shown when you add this trigger to a workflow).
3. (Recommended) Enable “Secret” and paste any random string. Record the same value in the trigger subscription’s *Webhook Secret* field so the plugin can validate signatures.
4. Enable the webhook.

If you manage webhooks through the Typeform API instead of the UI, set the `secret` field when creating or upserting the webhook. Use the same value inside Dify.

### Subscription Parameters

| Parameter | Description |
|-----------|-------------|
| `form_id` (optional) | Only forward responses whose `form_response.form_id` matches this value. Leave empty to accept responses from any form that posts to the endpoint. |
| `webhook_secret` (optional) | Shared secret used to verify the `Typeform-Signature` header. Must match the secret configured in Typeform. |

### Event Parameters

- `hidden_field_filter`: comma-separated `key=value` pairs matched against `form_response.hidden`.
- `variable_filter`: comma-separated `key=value` pairs matched against entries in `form_response.variables`.

If any filter fails, the event is ignored so your workflow doesn’t trigger.

## Supported Events

- `form_response_received` — fired for every Typeform webhook delivery (`event_type = "form_response"`).

### Payload Shape

The event output schema guarantees:

```json
{
  "event_id": "LtWXD3crgy",
  "event_type": "form_response",
  "form_response": {
    "form_id": "lT4Z3j",
    "token": "a3a12ec67a1365927098a606107fac15",
    "...": "..."
  }
}
```

All additional fields supplied by Typeform are preserved for downstream use (answers, definition, variables, hidden fields, etc.).