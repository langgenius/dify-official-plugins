# Twilio WhatsApp Integration Tool

## Overview

Twilio is a cloud communications platform that enables businesses to build, scale, and manage communication channels such as SMS, voice, video, email, and chat through its powerful APIs. With Twilio, developers can integrate advanced communication functionalities into their applications and services, facilitating seamless interactions with customers across multiple channels.

## Configure

To set up Twilio for WhatsApp integration, follow these steps:

### 1. Prerequisites
Before starting:
- Create a free [Twilio account](https://www.twilio.com/try-twilio).
- Obtain your **Account SID** and **Auth Token** from the Twilio Console.
- Have a WhatsApp-enabled phone for testing purposes.
- Install Docker and Docker Compose if using local development.

### 2. Configure Twilio Sandbox for WhatsApp
1. Log in to your Twilio Console.
2. Navigate to **Messaging > Senders > WhatsApp Senders**.
3. Enable the sandbox by sending the provided code to the displayed phone number via WhatsApp.
4. Note the sandbox phone number (e.g., `+14155238886`).

### 3. Set Up Your Application
1. Clone a sample repository or create your own backend using frameworks like FastAPI or Node.js.
2. In your project directory, create an `.env` file with the following variables:
```
TWILIO_NUMBER=whatsapp:+14155238886
TWILIO_ACCOUNT_SID=<Your Account SID>
TWILIO_AUTH_TOKEN=<Your Auth Token>
```
3. Use Twilio's SDK or REST API to handle incoming and outgoing messages:
  - Example (Node.js):
    ```javascript
    const twilio = require('twilio');
    const client = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);

    client.messages.create({
    body: 'Hello from Twilio!',
    from: 'whatsapp:+14155238886',
    to: 'whatsapp:+<Recipient Phone Number>'
    }).then(message => console.log(message.sid));
    ```
### 4. Webhook Configuration

1. Deploy your application on a public server or use tools like Localtunnel for local development.
2. In the Twilio Console:
    - Go to Phone Numbers > Active Numbers > Messaging Settings.
    - Add your webhook URL (e.g., `https://your-server-url/message`) under "A Message Comes In."

### 5. Test Your Integration

1. Send a message to your sandbox number from WhatsApp.
2. Observe the response from your application (e.g., auto-replies or chatbot interactions).