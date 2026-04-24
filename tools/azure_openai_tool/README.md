# Azure OpenAI Image Generation and Editing

## Overview

Azure OpenAI offers powerful AI models for generating and editing images based on text prompts. Dify has integrated tools leveraging these capabilities for general image generation/editing functions. This document outlines the steps to configure and use these Azure OpenAI image tools in Dify.

## Configure

### 1. Apply for an Azure OpenAI API Key

Please apply for an API Key on the [Azure OpenAI Platform](https://portal.azure.com/#home). This key will be used for all Azure OpenAI image tools.

In addition to the API Key, you will also need the following information to configure the plugin:

- **Deployment Name**: The name of your Azure OpenAI model deployment (e.g., `gpt-image-1`).
- **API Base URL**: The base URL of your Azure OpenAI resource (e.g., `https://********.openai.azure.com/`).

### 2. Get Azure OpenAI Image tools from Plugin Marketplace

The Azure OpenAI image tools (e.g., **GPT IMAGE**) can be found in the **Plugin Marketplace**.  
Please install the tools you need.

### 3. Fill in the configuration in Dify

On the Dify navigation page, click `Tools > [Installed Azure OpenAI Image Tool Name] > Authorize` and fill in the required fields.  
If you have multiple Azure OpenAI deployments, repeat this for each deployment.

The following fields are available for configuration:

| Field | Description | Example |
| --- | --- | --- |
| **API Key** | Your Azure OpenAI API key. | `********************************` |
| **Deployment Name** | The name of your Azure OpenAI model deployment. | `gpt-image-1` |
| **API Base URL** | The base URL of your Azure OpenAI resource. Use the endpoint up to the domain (do **not** include the model path or query parameters). | `https://********.openai.azure.com/` |
| **API Version** | The Azure OpenAI API version to use. To use the **Image Edit** feature, you must specify `2025-04-01-preview` or later. | `2025-04-01-preview` |

### 4. Use the tools

You can use the Azure OpenAI Image tools in the following application types:

#### Chatflow / Workflow applications

Both Chatflow and Workflow applications support nodes for the installed Azure OpenAI Image tools (e.g., `GPT Image Generate`). After adding a node, you need to fill in the necessary inputs (like "Prompt") with variables referencing user input or previous node outputs. Finally, use the variable to reference the image output by the tool in the "End" node or subsequent nodes.

#### Agent applications

Add the desired Azure OpenAI Image tools in the Agent application settings. Then, send a relevant prompt (e.g., an image description for generation, or an image and edit instruction) in the dialog box to call the appropriate tool.
