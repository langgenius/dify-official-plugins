# Azure OpenAI Image Generation and Editing

## Overview

Azure OpenAI offers powerful AI models for generating and editing images based on text prompts. Dify has integrated tools leveraging these capabilities, including GPT-IMAGE-1, and more general image generation/editing functions. This document outlines the steps to configure and use these Azure OpenAI image tools in Dify.

## Configure

### 1. Apply for an Azure OpenAI API Key

Please apply for an API Key on the [Azure OpenAI Platform](https://portal.azure.com/#home). This key will be used for all Azure OpenAI image tools.

**Important Note for GPT Image-1 Model:** If you plan to use the GPT-Image-1 model, your organization must complete verification first. Without organization verification, you'll receive a 403 error. To complete verification, please visit the [Azure OpenAI Service gpt-image-1](https://aka.ms/oai/gptimage1access).

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
