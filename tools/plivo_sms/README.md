# Plivo SMS

## Overview

This plugin sends SMS messages through the Plivo messaging platform from Dify workflows and agents.

## Configuration

1. Create or sign in to your Plivo account.
2. Copy the `auth_id` and `auth_token` from the Plivo console.
3. Install the plugin in Dify and fill in the credentials.

## Usage

Use the `send_sms` tool with:

- `from_number`: the Plivo number that sends the message
- `to_number`: the destination phone number
- `message`: the SMS content to send
