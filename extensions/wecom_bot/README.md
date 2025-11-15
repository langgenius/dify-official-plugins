# WeCom Bot Extension

This plugin mirrors the Slack bot integration but targets Enterprise WeChat (WeCom). It exposes an HTTP endpoint that you can configure in WeCom’s callback settings. Incoming encrypted events are validated/decrypted automatically, passed into a Dify App/Agent, and the generated answer is sent back to the original user through the WeCom message API.

## Features
- AES-CBC + SHA-1 verification compatible with the official WeCom callback spec.
- Handles both GET `echostr` handshake and POST message callbacks.
- Invokes any Dify app selected in the endpoint settings, just like the Slack bot.
- Sends replies via the `message/send` API (text messages for now, extensible later).

## Setup
1. Create a WeCom custom app and collect `CorpID`, `AgentID`, and the app secret.
2. Configure the endpoint settings inside Dify:
   - Token / EncodingAESKey / ReceiveID (CorpID or SuiteID)
   - CorpID + App Secret + AgentID
   - Target Dify app (the workflow that answers messages)
3. Deploy the plugin and copy the endpoint URL. Paste it into `应用管理 → 事件配置` as the callback URL. URL verification will succeed immediately if the token / AES key match.
4. Send a message to the WeCom app. The bot will forward it to the Dify app and send the answer back.

## Limitations
- Only text replies are implemented in this version. You can extend `wecom.py` to cover images/files/events.
- Access token caching is in-memory per process. If you scale horizontally, consider storing tokens in shared storage or re-request them for each call.
