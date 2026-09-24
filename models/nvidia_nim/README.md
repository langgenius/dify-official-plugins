# NVIDIA NIM

NVIDIA NIM, a set of easy-to-use inference microservices.

## Features
- Provides llm models in Dify.
- Supports customizable model configuration.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Get the required credentials from [NVIDIA NIM](https://www.nvidia.com/en-us/ai/).
3. Add the credentials in the plugin settings.
4. Save the configuration.

## Usage
Select **NVIDIA NIM** as the model provider in Dify, choose an available model, and use it in applications, agents, or workflows.

## Auto-discovery (NVIDIA Build)
When the **API Base URL** is left empty, the plugin automatically targets the
NVIDIA Build cloud catalog (`https://integrate.api.nvidia.com/v1`) — you only
need to paste your NVIDIA API key (`nvapi-...`).

During credential validation the plugin:
- lists the models served by the endpoint and checks the configured model
  name against it (typo suggestions included);
- falls back gracefully for self-hosted NIM endpoints that do not expose a
  model list;
- keeps the standard OpenAI-compatible ping as the authoritative check for
  the API key and model access.

Self-hosted NIM servers keep working as before: set the **API Base URL** to
your NIM endpoint (e.g. `http://192.168.1.100:8000/v1`) and leave the API key
empty if no authentication is configured.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. Review the upstream service's privacy policy before use.
