# Overview
OpenRouter is a powerful platform that provides access to a diverse set of language models, including both commercial and open-source options. It enables developers to integrate various AI capabilities such as text generation, image generation, audio processing, and more through a unified API. OpenRouter supports models like GPT-4, Anthropic's Claude, Google's Gemini, and many others, allowing users to leverage advanced AI functionalities in their applications.

This plugin supports language, text embedding, text rerank, text-to-speech, and speech-to-text models exposed by OpenRouter. Multimodal rerank models are not currently supported.

# Configuration
After installation, you need to get API keys from [OpenRouter](https://openrouter.ai/keys) and setup in Settings -> Model Provider.

![](_assets/openrouter.PNG)

## Kimi K3.1 Pro

`moonshotai/kimi-k3.1-pro` supports text, image, and video input, tools, structured
output, and configurable reasoning. Context and output limits, reasoning options,
and USD pricing follow the [OpenRouter model catalog](https://openrouter.ai/api/v1/models).
Highspeed is an upstream provider route for this model, rather than a separate model ID.

## Text-to-speech and speech-to-text

Text-to-speech models call OpenRouter's `/audio/speech` endpoint and always request
`mp3` output, the only format besides raw `pcm` that the endpoint returns. Models that
only return `pcm` (Gemini TTS, HeyGen Voice) are therefore not listed. Voice IDs are
copied from the [speech models API](https://openrouter.ai/api/v1/audio/speech/models),
and prices are per character of input text.

Speech-to-text models call `/audio/transcriptions` with base64 audio. The audio format
is detected from the file header. These two model types are available as predefined
models only.
