# Telegram Trigger Plugin Example

This example demonstrates how to build a Trigger plugin that automatically
registers a Telegram Bot API webhook using only a bot token. The
`TelegramSubscriptionConstructor` validates the token, provisions the webhook
(via `setWebhook`), and stores a secret token used to verify incoming updates.

## Features
- Bot token based subscription constructor (no manual callback URL pasting).
- Secret token validation for incoming webhooks.
- Event coverage for all Telegram [Bot API update types](https://core.telegram.org/bots/api#update), including business messages, reactions, inline queries, payments, polls, membership changes, and chat boosts.
- Structured output variables that mirror the official object schemas so they can be consumed directly in Dify workflows.

## Getting Started
1. Create a bot with [BotFather](https://core.telegram.org/bots#botfather) and copy the bot token.
2. Configure the plugin in Dify and select the Telegram trigger provider.
3. Provide the bot token during subscription creation; the webhook is created automatically.
4. Add any of the provided events (for example "Message Received", "Inline Query Received", or "Chat Boost Updated") to your workflow to process the corresponding updates.

For more details on trigger plugins, see the repository documentation and the
`provider/telegram.py` implementation.
