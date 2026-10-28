# Overview
OpenRouter is a powerful platform that provides access to a diverse set of language models, including both commercial and open-source options. It enables developers to integrate various AI capabilities such as text generation, image generation, audio processing, and more through a unified API. OpenRouter supports models like GPT-4, Anthropic's Claude, Google's Gemini, and many others, allowing users to leverage advanced AI functionalities in their applications.

This plugin supports language, text embedding, and text rerank models exposed by OpenRouter. Multimodal rerank models are not currently supported.

# Configuration
After installation, you need to get API keys from [OpenRouter](https://openrouter.ai/keys) and setup in Settings -> Model Provider.

![](_assets/openrouter.PNG)

## Kimi K3.1 Pro

`moonshotai/kimi-k3.1-pro` supports text, image, and video input, tools, structured
output, and configurable reasoning. Context and output limits, reasoning options,
and USD pricing follow the [OpenRouter model catalog](https://openrouter.ai/api/v1/models).
Highspeed is an upstream provider route for this model, rather than a separate model ID.
