# Stepfun

Official StepFun model provider plugin for Dify.

## Features
- Provides llm models in Dify.
- Adds predefined support for `step-3.7-flash`.
- Supports tool calling, reasoning controls, structured output, and multimodal input for Step 3.7 Flash.
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

## Usage
Select **Stepfun** as the model provider in Dify, choose an available model, and use it in applications, agents, or workflows.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. Review the upstream service's privacy policy before use.
