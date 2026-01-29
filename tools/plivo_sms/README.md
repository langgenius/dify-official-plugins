# Plivo SMS

## Overview

Plivo is a cloud communications platform that enables businesses to send SMS messages, make voice calls, and manage communications through powerful APIs. With Plivo, developers can integrate SMS messaging capabilities into their applications for notifications, alerts, two-factor authentication, and customer engagement.

You can use the Plivo SMS tool to send text messages to phone numbers worldwide using your Plivo account credentials.

## Configure

### 1. Prerequisites

Before starting:
- Create a [Plivo account](https://console.plivo.com/accounts/register/) (free trial available with credits for testing)
- Obtain your **Auth ID** and **Auth Token** from the [Plivo Console](https://console.plivo.com/dashboard/)
- Purchase or configure a Plivo phone number to send SMS from (required for production use)

### 2. Get Your Plivo Credentials

1. Log in to the [Plivo Console](https://console.plivo.com/)
2. On the Dashboard, locate your **Auth ID** and **Auth Token**
3. Copy these credentials for use in Dify

### 3. Get a Plivo Phone Number

To send SMS messages, you need a Plivo phone number:

1. In the Plivo Console, navigate to **Phone Numbers > Buy Numbers**
2. Select a number with SMS capability
3. Complete the purchase (trial accounts include free credits for testing)
4. Note the phone number in E.164 format (e.g., `+14155550100`)

**Note:** Trial accounts can only send SMS to verified phone numbers. Add destination numbers in the Plivo Console under **Phone Numbers > Sandbox Numbers**.

### 4. Configure Plivo SMS Tool in Dify

1. Install the **Plivo SMS** tool from the Dify Plugin Marketplace
2. Click **To authorize** and enter your credentials:
   - **Auth ID**: Your Plivo Auth ID from the console
   - **Auth Token**: Your Plivo Auth Token from the console

### 5. Use the Tool

You can use the Plivo SMS tool in the following application types:

#### Chatflow / Workflow Applications

Both Chatflow and Workflow applications support adding a **Plivo SMS** tool node.

Configure the tool parameters:
- **To Number**: The destination phone number in E.164 format (e.g., `+14155551234`)
- **From Number**: Your Plivo phone number in E.164 format (e.g., `+14155550100`)
- **Message**: The text content of the SMS message

#### Agent Applications

You can add the Plivo SMS tool to Agent applications for AI-driven messaging capabilities.

## Usage Notes

- **Phone Number Format**: All phone numbers must be in E.164 format, which includes the country code with a `+` prefix (e.g., `+1` for US/Canada, `+44` for UK)
- **Message Length**: Standard SMS messages are limited to 160 characters. Longer messages will be split into multiple segments
- **Character Encoding**: Messages containing non-GSM characters (like emoji or certain special characters) will use Unicode encoding, reducing the per-segment limit to 70 characters

## Example Use Cases

- **Notifications**: Send order confirmations, shipping updates, or appointment reminders
- **Alerts**: Deliver system alerts, security notifications, or monitoring alerts
- **Two-Factor Authentication**: Send OTP codes for user verification
- **Customer Engagement**: Send promotional messages or customer support updates

## Error Handling

The tool provides clear error messages for common issues:
- **Authentication Failed**: Verify your Auth ID and Auth Token are correct
- **Invalid Parameters**: Ensure phone numbers are in valid E.164 format
- **API Errors**: Check your Plivo account status and message credits

## Resources

- [Plivo Documentation](https://www.plivo.com/docs/)
- [Plivo SMS API Reference](https://www.plivo.com/docs/sms/api/message/)
- [Plivo Pricing](https://www.plivo.com/pricing/)
- [E.164 Phone Number Format](https://www.plivo.com/blog/e164-phone-number-formatting/)
