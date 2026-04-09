# Plivo Verify Plugin

OTP (One-Time Password) verification plugin for Dify using [Plivo's Verify API](https://www.plivo.com/verify/).

## Overview

This plugin enables phone number verification in your Dify workflows by sending OTP codes via SMS or voice call and validating user-entered codes.

## Setup

### Prerequisites

1. A [Plivo account](https://console.plivo.com/accounts/register/)
2. Your Plivo Auth ID and Auth Token (found in the [Plivo Console](https://console.plivo.com/dashboard/))

### Installation

1. In Dify, go to **Plugins** > **Explore Plugins**
2. Search for "Plivo Verify"
3. Click **Install**

### Configuration

After installation, configure the plugin with your Plivo credentials:

| Field | Description |
|-------|-------------|
| **Auth ID** | Your Plivo Auth ID from the console |
| **Auth Token** | Your Plivo Auth Token from the console |

## Tools

### send_otp

Sends an OTP code to a phone number.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `phone_number` | string | Yes | - | Destination phone number in E.164 format (e.g., `+14155551234`) |
| `channel` | select | No | `sms` | Delivery channel: `sms` or `voice` |
| `app_uuid` | string | No | - | Optional Plivo Verify application UUID for custom branding/settings |

#### Response

```json
{
  "status": "success",
  "session_id": "7a4351ec-679c-4df6-b6fb-0afde41f756b",
  "phone_number": "+14155551234",
  "channel": "sms"
}
```

The `session_id` is required for the subsequent `verify_otp` call.

---

### verify_otp

Validates an OTP code entered by the user.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | Yes | The session UUID returned from `send_otp` |
| `otp_code` | string | Yes | The OTP code entered by the user |

#### Response (Success)

```json
{
  "status": "success",
  "verified": true,
  "session_id": "7a4351ec-679c-4df6-b6fb-0afde41f756b"
}
```

#### Response (Failed)

```json
{
  "status": "failed",
  "verified": false,
  "session_id": "7a4351ec-679c-4df6-b6fb-0afde41f756b",
  "error": "invalid OTP"
}
```

## Workflow Integration

### Basic Verification Flow

```
┌─────────────────┐
│   Start Node    │  User provides phone number
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Send OTP      │  plivo_verify.send_otp
│                 │  Output: session_id
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  User Input     │  Ask user for the code
│                 │  they received via SMS
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Verify OTP    │  plivo_verify.verify_otp
│                 │  Input: session_id + otp_code
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   IF Condition  │  Check: verified == true
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
 Success    Failed
```

### Step-by-Step Setup

#### 1. Add Send OTP Node

Add a **Tool** node and select `plivo_verify > send_otp`:

- **phone_number**: `{{start.phone_number}}` (from user input)
- **channel**: `sms` (or `voice` for phone call)

#### 2. Add User Input Node

Add a **Question** node to collect the OTP code:

- **Question**: "Please enter the 6-digit verification code sent to your phone"
- **Variable name**: `otp_code`

#### 3. Add Verify OTP Node

Add another **Tool** node and select `plivo_verify > verify_otp`:

- **session_id**: `{{send_otp.session_id}}`
- **otp_code**: `{{question.otp_code}}`

#### 4. Add Conditional Branch

Add an **IF/Else** node:

- **Condition**: `{{verify_otp.verified}}` equals `true`
- **If true**: Continue to success path (e.g., create account)
- **If false**: Show error message or retry

### Variable Reference

| Variable | Source | Description |
|----------|--------|-------------|
| `{{send_otp.session_id}}` | send_otp output | Session UUID for verification |
| `{{send_otp.phone_number}}` | send_otp output | The phone number used |
| `{{send_otp.channel}}` | send_otp output | Channel used (sms/voice) |
| `{{verify_otp.verified}}` | verify_otp output | Boolean verification result |
| `{{verify_otp.status}}` | verify_otp output | "success" or "failed" |

## Use Cases

### Account Registration

Verify phone numbers during user signup to prevent fake accounts.

### Two-Factor Authentication (2FA)

Add an extra security layer by requiring OTP verification for sensitive actions.

### Password Reset

Verify user identity before allowing password changes.

### Transaction Confirmation

Confirm high-value transactions with OTP verification.

## Advanced Configuration

### Custom Verify Application

To customize OTP settings (brand name, code length, expiry time), create a Verify Application in the [Plivo Console](https://console.plivo.com/verify/applications/):

1. Go to **Verify > Applications**
2. Click **Create Application**
3. Configure settings:
   - **Brand Name**: Displayed in SMS (e.g., "YourApp")
   - **Code Length**: 4-8 digits
   - **Code Expiry**: How long the code is valid
   - **Retry Settings**: Auto-retry configuration
4. Copy the **App UUID**
5. Use it in the `app_uuid` parameter of `send_otp`

### Voice Channel

For users who can't receive SMS, use the `voice` channel:

```
channel: voice
```

The OTP code will be read aloud in a phone call.

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| "Authentication failed" | Invalid Auth ID or Token | Check credentials in Plivo Console |
| "Invalid request parameters" | Malformed phone number | Use E.164 format (+1234567890) |
| "OTP verification failed" | Wrong code or expired | Ask user to re-enter or resend OTP |

## Pricing

Plivo Verify API charges per verification attempt. See [Plivo Pricing](https://www.plivo.com/pricing/) for current rates.

## Support

- [Plivo Verify Documentation](https://www.plivo.com/docs/verify/)
- [Plivo Support](https://support.plivo.com/)
- [Dify Documentation](https://docs.dify.ai/)
