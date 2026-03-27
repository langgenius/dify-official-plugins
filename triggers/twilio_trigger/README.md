# Twilio Trigger Plugin for Dify

A Dify plugin that triggers workflows when receiving SMS messages, voice calls, or WhatsApp messages via Twilio.

## Features

- **SMS Received**: Trigger workflows when SMS messages are received
- **Call Received**: Trigger workflows when voice calls are received
- **WhatsApp Received**: Trigger workflows when WhatsApp messages are received

## Setup

### Prerequisites

1. A Twilio account with Account SID and Auth Token
2. A Twilio phone number with SMS and/or Voice capabilities
3. For WhatsApp: A Twilio WhatsApp-enabled number or WhatsApp Business API setup

### Configuration

1. In Dify, add the Twilio Trigger plugin
2. Enter your Twilio credentials:
   - **Account SID**: Your Twilio Account SID (starts with `AC`)
   - **Auth Token**: Your Twilio Auth Token
3. Select a phone number from the dropdown
4. Choose the events you want to trigger on

## Events

### SMS Received

Triggered when an SMS message is received on your Twilio phone number.

**Filter Parameters:**
- `from_filter`: Comma-separated phone numbers to filter by sender
- `body_contains`: Filter messages containing specific text (case-insensitive)
- `body_regex`: Filter messages matching a regex pattern

**Output Variables:**
- `MessageSid`: Unique message identifier
- `From`: Sender phone number
- `To`: Recipient phone number
- `Body`: Message content
- `NumMedia`: Number of media attachments
- Location info: `FromCity`, `FromState`, `FromCountry`, etc.

### Call Received

Triggered when a voice call is received on your Twilio phone number.

**Filter Parameters:**
- `from_filter`: Comma-separated phone numbers to filter by caller
- `call_status_filter`: Comma-separated call statuses to filter (e.g., `ringing,in-progress,completed`)

**Output Variables:**
- `CallSid`: Unique call identifier
- `From`: Caller phone number
- `To`: Recipient phone number
- `CallStatus`: Call status (queued, ringing, in-progress, completed, busy, failed, no-answer, canceled)
- `Direction`: Call direction (inbound, outbound-api, outbound-dial)
- `CallerName`: Caller ID name (if available)
- Location info: `FromCity`, `FromState`, `FromCountry`, etc.

### WhatsApp Received

Triggered when a WhatsApp message is received on your Twilio phone number.

**Filter Parameters:**
- `from_filter`: Comma-separated WhatsApp numbers to filter (format: `whatsapp:+1234567890`)
- `body_contains`: Filter messages containing specific text (case-insensitive)
- `body_regex`: Filter messages matching a regex pattern
- `profile_name_filter`: Comma-separated WhatsApp profile names to filter

**Output Variables:**
- `MessageSid`: Unique message identifier
- `From`: Sender WhatsApp number (format: `whatsapp:+1234567890`)
- `To`: Recipient WhatsApp number
- `Body`: Message content
- `ProfileName`: Sender's WhatsApp profile name
- `WaId`: WhatsApp ID of the sender
- `NumMedia`: Number of media attachments
- Location sharing: `Latitude`, `Longitude`, `Address`, `Label`
- Button interactions: `ButtonText`, `ButtonPayload`

## Security

The plugin validates incoming webhook requests using Twilio's request signature verification (X-Twilio-Signature header) to ensure requests are genuinely from Twilio.

## License

MIT
