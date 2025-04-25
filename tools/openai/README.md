# OpenAI Image Generation and Editing

## Overview

OpenAI offers powerful AI models for generating and editing images based on text prompts. Dify has integrated tools leveraging these capabilities, including DALL-E 2, DALL-E 3 and GPT-IMAGE-1, and more general image generation/editing functions. This document outlines the steps to configure and use these OpenAI image tools in Dify.

## Configure

### 1. Apply for an OpenAI API Key

Please apply for an API Key on the [OpenAI Platform](https://platform.openai.com/). This key will be used for all OpenAI image tools.

**Important Note for GPT Image-1 Model:** If you plan to use the GPT-Image-1 model, your organization must complete verification first. Without organization verification, you'll receive a 403 error. To complete verification, please visit the [API Organization Verification guide](https://help.openai.com/en/articles/10910291-api-organization-verification).

### 2. Get OpenAI Image tools from Plugin Marketplace

The OpenAI Image tools (including DALL-E and GPT IMAGE) can be found in the Plugin Marketplace. Please install the ones you need.

### 3. Fill in the configuration in Dify

On the Dify navigation page, click `Tools > [Installed OpenAI Image Tool Name, e.g., DALL-E 3] > Authorize` and fill in the API Key. Repeat this for each OpenAI image tool you install.

**Note:** Base URL and Organization ID are optional. The Organization IDs can be found on your [Organization settings](https://platform.openai.com/settings/organization/general) page.

![OpenAI Image Tool Configuration](./_assets/openai_1.PNG) 
*(Note: Image may show DALL-E specifically, but the process is similar for other OpenAI image tools)*

### 4. Use the tools

You can use the OpenAI Image tools in the following application types:

#### Chatflow / Workflow applications

![Chatflow/Workflow Application](./_assets/openai_2.PNG)

Both Chatflow and Workflow applications support nodes for the installed OpenAI Image tools (e.g., `DALL-E 3`, `GPT Image Generate`). After adding a node, you need to fill in the necessary inputs (like "Prompt") with variables referencing user input or previous node outputs. Finally, use the variable to reference the image output by the tool in the "End" node or subsequent nodes.

#### Agent applications

![Agent Application](./_assets/openai_3.PNG)

Add the desired OpenAI Image tools in the Agent application settings. Then, send a relevant prompt (e.g., an image description for generation, or an image and edit instruction) in the dialog box to call the appropriate tool.
