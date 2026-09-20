# Stepfun

Official StepFun model provider plugin for Dify.

## Features
- Provides llm models in Dify.
- Adds predefined support for `step-5-preview` and `step-3.7-flash`.
- Supports tool calling, reasoning controls, structured output, and multimodal input for Step 5 Preview and Step 3.7 Flash.
- Supports predefined model and customizable model configuration.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Get the required credentials from [Stepfun](https://platform.stepfun.com/interface-key).
   - **Note:** StepFun operates two separate platforms:
     - **Standard platform** at [platform.stepfun.com](https://platform.stepfun.com) (uses `api.stepfun.com` endpoint - default)
     - **International platform** at [platform.stepfun.ai](https://platform.stepfun.ai) (uses `api.stepfun.ai` endpoint)
   - These are separate account systems. An API key from one platform will not work with the other endpoint.
3. Add the credentials in the plugin settings.
   - If your API key is from the international platform (platform.stepfun.ai), enable the **Use International Endpoint** option.
4. Save the configuration.

`Enable request metadata` is optional and disabled by default. Turning it on attaches `X-Dify-App-Id` and `X-Dify-Source` to each StepFun request as custom HTTP headers, so usage can be attributed to a specific Dify app. The opt-in is routed through the `extra_headers` credential because the SDK's OAICompat base class does not forward body-level metadata to the upstream request. The Dify session lookup is best-effort: if the session context is not initialized, no headers are attached and the request is sent unchanged.

## Usage
Select **Stepfun** as the model provider in Dify, choose an available model, and use it in applications, agents, or workflows.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. Review the upstream service's privacy policy before use.

## Step 5 Preview

Supports a 1M-token context window and up to 1M output tokens (input and output share the context budget), text/image/video input, tool calling, JSON output, and low/medium/high reasoning effort. Reasoning is displayed in both streaming and non-streaming responses.

The listed price is the standard platform's uncached rate: RMB 7 per million input tokens and RMB 20 per million output tokens. Cached input and international pricing may differ.

Sources: [model specifications](https://platform.stepfun.com/docs/zh/guides/models/step-5-preview), [Chat Completions API](https://platform.stepfun.com/docs/zh/api-reference/chat/chat-completion-create), and [pricing](https://platform.stepfun.com/docs/zh/guides/pricing/details).
