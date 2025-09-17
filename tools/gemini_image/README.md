# Gemini Image

## Overview

The **Gemini Image Tool** is used to access Gemini's image generation and editing models on Vertex AI.

---

## Configuration

### 1. Get a Google Cloud API key

1. Go to the [Google Cloud ](https://cloud.google.com/vertex-ai/generative-ai/docs/start/api-keys?usertype=existinguser).  
2. Follow the steps to create an API key.  


### 3. Gemini Image Tool in Dify

1. In the **Dify Console**, go to **Plugin Marketplace**.  
2. Search for **Gemini Image** and install it.

### 4. Configure in Dify

In **Dify Console > Tools > Gemini Image > Authorize**, enter:  

- **Vertex Service Account key**: The key from [Google Cloud](https://ai.google.dev/gemini-api/docs/api-key) in base64 format.  
- **project ID**: The [Google Cloud project ID](https://cloud.google.com/resource-manager/docs/creating-managing-projects#identifying_projects).  
- **vertex_location**: The [Google model endpoint location](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations).
---

## Usage

The Gemini Image Tool can be used in the following application types:

### Chatflow / Workflow Applications
Add a **Gemini Image node** to generate or edit images during flow execution.

### Agent Applications
Enable the **Gemini Image tool** in Agent applications.  

