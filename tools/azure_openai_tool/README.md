# Azure OpenAI Image Generation and Editing

## Overview

Azure OpenAI offers powerful AI models for generating and editing images based on text prompts. Dify has integrated tools leveraging these capabilities for general image generation/editing functions. This document outlines the steps to configure and use these Azure OpenAI image tools in Dify.

## Configure

### 1. Apply for an Azure OpenAI API Key

Please apply for an API Key on the [Azure OpenAI Platform](https://portal.azure.com/#home). This key will be used for all Azure OpenAI image tools.

**Important Note:** When configuring the plugin, you need to specify your Azure OpenAI image model deployment name (e.g., gpt-image-1/1.5) in the **Deployment Name** field. This deployment name will be used for both image generation and editing operations.

### 2. Get Azure OpenAI Image tools from Plugin Marketplace

The Azure OpenAI image tools (e.g., **GPT IMAGE**) can be found in the **Plugin Marketplace**.  
Please install the tools you need.

### 3. Fill in the configuration in Dify

On the Dify navigation page, click `Tools > [Installed Azure OpenAI Image Tool Name] > Authorize` and fill in the API Key. Repeat this for each Azure OpenAI image tool you install.

### 4. Use the tools

You can use the Azure OpenAI Image tools in the following application types:

#### Chatflow / Workflow applications

Both Chatflow and Workflow applications support nodes for the installed Azure OpenAI Image tools (e.g., `GPT Image Generate`). After adding a node, you need to fill in the necessary inputs (like "Prompt") with variables referencing user input or previous node outputs. Finally, use the variable to reference the image output by the tool in the "End" node or subsequent nodes.

#### Agent applications

Add the desired Azure OpenAI Image tools in the Agent application settings. Then, send a relevant prompt (e.g., an image description for generation, or an image and edit instruction) in the dialog box to call the appropriate tool.
