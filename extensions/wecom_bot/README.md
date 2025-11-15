# WeCom Bot Extension

This plugin mirrors the Slack bot integration but targets Enterprise WeChat (WeCom). It exposes an HTTP endpoint that you can configure in WeCom’s callback settings. Incoming encrypted events are validated/decrypted automatically, passed into a Dify App/Agent, and the generated answer is sent back to the original user through the WeCom message API.

## Features
- AES-CBC + SHA-1 verification compatible with the official WeCom callback spec.
- Separate GET/POST endpoints: GET responds to the initial `echostr` challenge, POST decrypts messages and re-encrypts answers.
- Invokes any Dify App/Agent selected in the settings and returns the answer as an encrypted HTTP response (no additional WeCom API calls required).

## Setup
1. Create a WeCom custom app and collect `CorpID`, `AgentID`, and the app secret.
2. Configure the endpoint settings inside Dify:
   - Token / EncodingAESKey / ReceiveID (CorpID or SuiteID)
   - CorpID + App Secret + AgentID
   - Target Dify app (the workflow that answers messages)
3. Deploy the plugin and copy the endpoint URL(s). Use the same path for both GET & POST; paste it into `应用管理 → 事件配置` as the callback URL. URL verification will succeed immediately if the token / AES key match.
4. Send a message to the WeCom app. The bot forwards it to the Dify app and returns the AI answer in the encrypted HTTP response.

## Limitations
- Only text replies are implemented in this version. You can extend `wecom_message.py` to cover images/files/events.
