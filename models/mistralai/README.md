# Overview
Mistral AI provides a cutting-edge platform for developing and deploying state-of-the-art generative AI models. It supports developers and businesses by offering customizable AI solutions that can be fine-tuned to meet specific needs.

## Available Models

### Premier Models
- **Magistral Medium** - Advanced model with 40k context
- **Mistral Medium** - Frontier-class multimodal model with 128k context
- **Mistral Large** - Top-tier model for high-complexity tasks
- **Pixtral Large** - Vision-capable large model with frontier capabilities
- **Codestral** - Cutting-edge language model for coding (256k context)
- **Mistral Saba** - Specialized model for Middle East and South Asia languages
- **Ministral 8B/3B** - Powerful edge models for on-device use cases

### Free/Open Source Models
- **Magistral Small** - Small model with transparent multilingual capabilities
- **Mistral Small** - SOTA multimodal multilingual model with vision capabilities (Apache 2.0)
- **Devstral Small** - Best open-source model for coding agents
- **Pixtral 12B** - Vision-capable small model
- **Mistral Nemo** - Best multilingual open source model
- **Codestral Mamba** - First mamba 2 open source model

### Research Models
- **Mathstral** - First math open source model (Apache 2.0)

### Embedding Models
- **Mistral Embed** - State-of-the-art semantic embeddings for text
- **Codestral Embed** - Specialized embeddings for code representation

### Moderation Models
- **Mistral Moderation** - Content moderation service for detecting harmful text across multiple policy dimensions

### Services Not Supported in Dify
- **Mistral OCR** - OCR service for extracting text and images from documents (uses `/v1/ocr` endpoint, not compatible with Dify's model framework)

## Model Versions

For maximum flexibility, we provide both **Latest** and **Dated** versions of each model:

### 🔄 **Latest Versions** (Recommended)
- **Format**: `model-name-latest` (e.g., `mistral-large-latest`)
- **Behavior**: Automatically points to the most recent version
- **Use Case**: Development, testing, and applications that benefit from automatic updates
- **Advantage**: Always get the latest improvements and features

### 📅 **Dated Versions** (Stable)
- **Format**: `model-name-YYMM` (e.g., `mistral-large-2411`)
- **Behavior**: Fixed to a specific model version
- **Use Case**: Production environments requiring reproducible results
- **Advantage**: Guaranteed consistency and predictable behavior

### 💡 **Which Version to Choose?**
- **Use Latest** for: Development, experimentation, staying current with improvements
- **Use Dated** for: Production deployments, research requiring reproducibility, compliance requirements

## Magistral Models

**Magistral** models (Magistral Medium and Magistral Small) are designed for complex problem-solving and feature seamless integration with Dify.

### 🎯 **Model Configuration**

Magistral models are designed for step-by-step problem solving and analytical tasks.

### 🔧 **Reasoning Mode Parameter**

Magistral models support a **`reasoning_mode`** boolean parameter that controls how the model processes requests:

- **`reasoning_mode: true`** (Default): Enables reasoning mode with system prompt for step-by-step problem solving
- **`reasoning_mode: false`**: Disables reasoning mode for standard chat behavior without system prompt

This parameter is automatically transformed to the Mistral AI API `prompt_mode` parameter (`"reasoning"` or `null`) based on your selection.


# Configure
After installation, you need to get API keys from [MistralAI](https://console.mistral.ai/api-keys/) and setup in Settings -> Model Provider.

![](_assets/mistralai.PNG)
