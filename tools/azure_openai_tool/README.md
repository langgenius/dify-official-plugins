# Azure OpenAI Image Generation and Editing

## Overview

Azure OpenAI offers GPT-image series models for generating and editing images from text and image inputs. This plugin supports Azure OpenAI image generation and edit workflows with current GPT-image deployments, including the latest `gpt-image-2` deployments. For deployments that support additional output resolutions, choose `Custom` in the size selector of the existing image tools and then provide the optional `custom_size` parameter. This document outlines the steps to configure and use these Azure OpenAI image tools in Dify.

## Configure

### 1. Apply for an Azure OpenAI API Key

Please apply for an API Key on the [Azure OpenAI Platform](https://portal.azure.com/#home). This key will be used for all Azure OpenAI image tools.

In addition to the API Key, you will also need the following information to configure the plugin:

- **Deployment Name**: The name of your Azure OpenAI GPT-image deployment (for example, `gpt-image-2`).
- **API Base URL**: The base URL of your Azure OpenAI resource (e.g., `https://********.openai.azure.com/`).

### 2. Get Azure OpenAI Image tools from Plugin Marketplace

The Azure OpenAI image tools (for example, **Azure OpenAI Image Generate** and **Azure OpenAI Image Edit**) can be found in the **Plugin Marketplace**.  
Please install the tools you need.

### 3. Fill in the configuration in Dify

On the Dify navigation page, click `Tools > [Installed Azure OpenAI Image Tool Name] > Authorize` and fill in the required fields.  
If you have multiple Azure OpenAI deployments, repeat this for each deployment.

The following fields are available for configuration:

| Field | Description | Example |
| --- | --- | --- |
| **API Key** | Your Azure OpenAI API key. | `********************************` |
| **Deployment Name** | The deployment name of your Azure OpenAI GPT-image series model. | `gpt-image-2` |
| **API Base URL** | The base URL of your Azure OpenAI resource. Use the endpoint up to the domain (do **not** include the model path or query parameters). | `https://********.openai.azure.com/` |
| **API Version** | The Azure OpenAI API version to use. For current GPT-image edit support, use `2025-04-01-preview` or later. | `2025-04-01-preview` |

### 4. Use the tools

You can use the Azure OpenAI Image tools in the following application types:

#### Chatflow / Workflow applications

Both Chatflow and Workflow applications support nodes for the installed Azure OpenAI Image tools (for example, `Azure OpenAI Image Generate` and `Azure OpenAI Image Edit`). After adding a node, you need to fill in the necessary inputs (like "Prompt") with variables referencing user input or previous node outputs. Finally, use the variable to reference the image output by the tool in the "End" node or subsequent nodes. If your deployment supports custom GPT-image sizes, set `Image size` to `Custom`, then provide `custom_size` with a value like `1024x1024`.

#### Agent applications

Add the desired Azure OpenAI Image tools in the Agent application settings. Then, send a relevant prompt (for example, an image description for generation, or an image plus an edit instruction) in the dialog box to call the appropriate tool. If your provider configuration points to a `gpt-image-2` deployment, you can keep using the same tools and set `Image size` to `Custom` when you need a resolution that is not covered by the preset selector, then fill in `custom_size`. Azure documentation describes variation-style workflows through image editing and inpainting, so this plugin exposes generation and editing tools rather than a separate variation endpoint tool.
