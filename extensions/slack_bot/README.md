## Slack Bot

**Author:** Langgenius  
**Version:** 0.0.1
**Type:** extension

### Description

Follow these steps to integrate the Slack plugin:

1. **Create a Slack App**

   - Either create an app from a manifest or from scratch
   - Name your app and select your target workspace
     <img src="./_assets/step1.png" width="600" />
     <img src="./_assets/step2.png" width="600" />

2. **Configure App Settings**

   - Enable Incoming Webhooks
   - Install the app to your workspace
   - Choose a channel for message delivery
   - Locate your "Bot User OAuth Token" in settings
     <img src="./_assets/step3.png" width="600" />
     <img src="./_assets/step4.png" width="600" />
     <img src="./_assets/step5.png" width="600" />

3. **Set Up Dify Endpoint**

   - Create a new endpoint with a custom name
   - Input your Bot User OAuth Token
   - Optionally specify a Channel ID to restrict the bot to a specific channel
   - Select Event Types to determine how the bot responds:
     - App Mentions Only: Bot only responds when directly mentioned
     - Channel Messages: Bot responds to all messages in the channel
     - Both Mentions and Messages: Bot responds to both mentions and regular messages
   - Set "Allow Retry" to false (recommended to prevent duplicate messages)
   - Link to your Dify chatflow/chatbot/agent
   - Save and copy the generated endpoint URL

    <div style="display: flex; gap: 10px;">
      <img src="./_assets/step6.png" width="400" />
      <img src="./_assets/step7.png" width="400" />
    </div>

4. **Complete Slack App Configuration**

   - Enable Event Subscriptions
   - Paste the Dify endpoint URL as the Request URL
   - Add required OAuth scopes for Event Subscriptions
   - Configure App's OAuth & Permissions with necessary scopes
     - For file handling, ensure you add `files:read` scope
     - For responding to channel messages, add `channels:history` scope
     <img src="./_assets/step8.png" width="600" />
     <img src="./_assets/step9.png" width="600" />

     <img src="./_assets/step10.png" width="400" />

5. **Final Steps**
   - Reinstall the app to your workspace if you made changes
   - Add the bot to your chosen channel
   - Start interacting by @mentioning the bot in messages or sending regular messages (depending on your event type selection)
   - The bot can now recognize when files are attached to messages
     <img src="./_assets/step11.png" width="600" />
     <img src="./_assets/step12.png" width="600" />

### New Features

- **Channel Selection**: You can now specify a particular Slack channel ID for the bot to monitor. Leave this field empty to have the bot respond to events from all channels.
- **Event Type Selection**: Choose which types of events the bot should respond to:
  - App Mentions Only: The bot only responds when directly mentioned with @
  - Channel Messages: The bot responds to all messages in the channel
  - Both: The bot responds to both mentions and regular messages
- **File Handling**: The bot can now recognize when files are attached to messages and will acknowledge them in its response.
