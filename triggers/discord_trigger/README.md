# Discord Trigger

## Overview

Discord Webhook Events are outgoing webhooks sent by Discord when selected events happen for your application. This trigger receives those signed HTTP events and starts Dify workflows with a normalized payload.

This is different from Discord Incoming Webhooks, which are used to send messages into a channel. The Discord tool under `tools/discord` handles message sending; this trigger handles events coming from Discord.

## Configuration

### 1. Create or open a Discord application

Open the [Discord Developer Portal](https://discord.com/developers/applications), then create or select your application.

### 2. Copy the application public key

In your application's **General Information** page, copy the **Public Key**. Paste it into the trigger's `Application Public Key` field in Dify.

The trigger uses this key to verify the `X-Signature-Ed25519` and `X-Signature-Timestamp` headers Discord sends with every Webhook Event request.

### 3. Create a Dify Discord trigger

In Dify, create a Discord trigger subscription and select the Discord Webhook Event types you want to receive. Leave the event type list empty to accept all Discord Webhook Events.

Copy the endpoint URL that Dify provides for the trigger subscription.

### 4. Configure Discord Webhook Events

In the Discord Developer Portal, open your application's **Webhooks** page.

Paste the Dify endpoint URL into the **Endpoint URL** field, enable **Events**, then select the same event types you configured in Dify.

Discord validates the URL by sending a signed `PING` payload. This trigger responds with HTTP `204` and an empty body, as required by Discord Webhook Events.

## Output

The trigger emits a single event named `webhook_event`.

Workflow variables include:

- `version`
- `application_id`
- `webhook_type`
- `event_type`
- `timestamp`
- `data`
- `raw_payload`
- `user_id`, `guild_id`, `entitlement_id`, `lobby_id`, and `message_id` when Discord includes them

## Supported Webhook Event Types

- `APPLICATION_AUTHORIZED`
- `APPLICATION_DEAUTHORIZED`
- `ENTITLEMENT_CREATE`
- `ENTITLEMENT_UPDATE`
- `ENTITLEMENT_DELETE`
- `QUEST_USER_ENROLLMENT`
- `LOBBY_MESSAGE_CREATE`
- `LOBBY_MESSAGE_UPDATE`
- `LOBBY_MESSAGE_DELETE`
- `GAME_DIRECT_MESSAGE_CREATE`
- `GAME_DIRECT_MESSAGE_UPDATE`
- `GAME_DIRECT_MESSAGE_DELETE`

## Notes

Discord Webhook Events are not Gateway events. They do not provide the full set of Discord message and guild events. For ordinary channel message listening, Discord requires a Gateway connection with a bot token and intents, which is intentionally out of scope for this trigger.
