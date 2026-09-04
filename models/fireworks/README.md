# Fireworks AI

Fireworks AI provides hosted generative and embedding models that can be used directly from Dify.

## Features
- Provides llm, text-embedding models in Dify.
- Includes predefined llm models such as llama-v3-70b-instruct, mixtral-8x7b-instruct, llama-v3-8b-instruct.
- Includes predefined text embedding models such as UAE-Large-V1, nomic-embed-text-v1, gte-large.
- Supports predefined model and customizable model configuration.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Get the required credentials from [Fireworks AI](https://fireworks.ai/account/api-keys).
3. Add the credentials in the plugin settings.
4. Save the configuration.

## Configuration Options

### Attach Dify app_id as request metadata
This plugin offers an optional **Attach Dify app_id as request metadata** credential that is disabled by default. When enabled, the plugin attaches the current Dify `app_id` and a `dify` source marker as a `metadata` field via the `extra_body` argument to the underlying `openai` SDK call.

The Fireworks API is OpenAI-compatible and silently ignores unknown body fields, so the metadata travels alongside the rest of the request payload and is used for observability / proxy-side propagation. Fireworks does not currently consume the metadata. Default is `disabled`, so the request shape is unchanged unless you opt in.

## Usage
Select **Fireworks AI** as the model provider in Dify, choose an available model, and use it in applications, agents, or workflows.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. Review the upstream service's privacy policy before use.
