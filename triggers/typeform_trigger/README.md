# Typeform Trigger Plugin

Dify trigger plugin that listens for Typeform `form_response` webhooks. Each submission is forwarded to your workflow with the full response payload so you can automate follow-up actions in real time.

## Quick Start

1. Install the plugin in your Dify workspace and drag the trigger into a workflow.
2. Choose how you want to connect (manual webhook, Personal Access Token, or OAuth).
3. Select the Typeform you want to listen to (required for API Key / OAuth modes, optional filter when manual).
4. Save the workflow and submit a test response in Typeform to confirm events arrive in Dify.

## Connection Modes

### Manual webhook (copy & paste)

1. Open your Typeform form → **Connect** → **Webhooks**.
2. Add a new webhook using the Dify endpoint (shown when you add this trigger to a workflow).
3. (Recommended) Enable “Secret” and paste any random string. Record the same value in the trigger subscription’s *Webhook Secret* field so the plugin can validate signatures.
4. Enable the webhook and submit a test response to confirm you receive a `2xx`.

> If you manage webhooks through the Typeform API instead of the UI, set the `secret` field when creating or upserting the webhook. Use the same value inside Dify.

### Auto-managed webhook via Personal Access Token

1. In Dify, choose **Connect with API Key** when configuring the trigger.
2. Generate a Typeform Personal Access Token with the `forms:read`, `webhooks:read`, and `webhooks:write` scopes (Account → Personal tokens).
3. Paste the token in the trigger configuration. Dify will fetch your forms and display a dynamic dropdown.
4. Select the form you want to subscribe to. You can optionally override the generated webhook secret.
5. Dify creates (or updates) the webhook in Typeform and stores the secret for signature validation.

### Auto-managed webhook via OAuth 2.0

1. Create an application in the [Typeform Developer Portal](https://developer.typeform.com/my-apps) and enable the `forms:read`, `webhooks:read`, `webhooks:write`, and `offline` scopes.
2. Enter the app’s client ID and client secret in the trigger configuration, then click **Connect with OAuth**.
3. Complete the Typeform consent flow. Dify exchanges the code for tokens (and keeps the refresh token so it can renew expired access tokens).
4. Pick the target form from the dynamic dropdown and optionally override the generated secret.
5. Dify provisions the webhook in Typeform using your OAuth credentials.

### Subscription Parameters

| Parameter | When used | Description |
|-----------|-----------|-------------|
| `form_id` | Always optional | Filters to a single form when you manage webhooks manually. In API Key / OAuth modes this field becomes a dynamic dropdown and is required. |
| `webhook_secret` | Always optional | Shared secret used to verify the `Typeform-Signature` header when you configure the webhook manually. |
| `webhook_secret` override | API Key & OAuth | Lets you supply a custom secret instead of letting Dify generate one when it creates the webhook for you. |

When Dify creates the webhook on your behalf it stores the generated (or overridden) secret in the subscription so signature validation works automatically.

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

## Directory Structure

| Path | Purpose |
|------|---------|
| `main.py` | Minimal entrypoint invoked by the Dify plugin runtime. |
| `manifest.yaml` | Describes plugin metadata, runtime configuration, and versioning. |
| `provider/typeform_simple.yaml` | Declarative trigger configuration (parameters, credentials, events). |
| `provider/typeform_simple.py` | Trigger implementation handling webhooks, credentials, and API calls. |
| `events/form/form_response_received.yaml` | Event schema exposed to workflows. |
| `_assets/` | Icons referenced by the manifest for marketplace presentation. |

## Troubleshooting

- **OAuth sign-in fails**: confirm the redirect URI matches the one shown in Dify and that the Typeform app grants `forms:read`, `webhooks:read`, `webhooks:write`, and `offline`.
- **Form dropdown empty**: the access token must include `forms:read`; regenerate the Personal Access Token or re-authorise via OAuth.
- **Workflow never triggers**: ensure the Typeform webhook shows “Enabled”, the trigger is active in Dify, and the same webhook secret is configured on both sides.
- **Signature validation errors**: rotate the webhook secret in Typeform and paste the new value into Dify (manual mode) or reconnect so Dify can regenerate it (API Key / OAuth).
## References

- [Typeform Webhooks API Documentation](https://www.typeform.com/developers/webhooks/)
- [Typeform Webhook Security Guide](https://www.typeform.com/developers/webhooks/secure-your-webhooks/)
- [Typeform Personal Access Tokens](https://admin.typeform.com/account#/section/tokens)
- [Typeform OAuth Scopes](https://www.typeform.com/developers/webhooks/secure-your-webhooks/#oauth-scopes)
- [Example Webhook Payload](https://www.typeform.com/developers/webhooks/example-webhook-payload/)
- [Typeform Developers Community](https://www.typeform.com/developers/community/)
