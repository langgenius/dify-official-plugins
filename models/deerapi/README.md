# DeerAPI Dify Plugin

A comprehensive AI model aggregation platform providing unified access to leading AI models through OpenAI-compatible APIs.

## Overview

DeerAPI is a one-stop AI model API platform that aggregates mainstream AI capabilities including text generation, image processing, audio, and video generation. The platform provides unified OpenAI-style interfaces, enabling developers to integrate quickly and support rapid iteration for global business deployment.

## Supported Models

### OpenAI
- **GPT Models**: GPT-3.5 Turbo, GPT-4, GPT-4 Turbo, GPT-4o, GPT-4o Mini
- **Advanced Models**: GPT-5, GPT-4.1, O1 Series (O1, O1 Mini, O1 Preview)
- **Reasoning Models**: O3, O3 Mini, O3 Pro, O4 Mini
- **Legacy Models**: GPT-3.5 Turbo variants, GPT-4 variants
- **Audio**: Whisper (Speech-to-Text), TTS (Text-to-Speech)
- **Embeddings**: text-embedding-3-large, text-embedding-3-small, text-embedding-ada-002

### Anthropic Claude
- **Claude 3 Family**: Claude 3 Haiku, Claude 3 Sonnet, Claude 3 Opus
- **Claude 3.5**: Claude 3.5 Haiku, Claude 3.5 Sonnet
- **Claude 3.7**: Claude 3.7 Sonnet
- **Claude 4**: Claude Opus 4, Claude Sonnet 4
- **Latest Models**: Including reasoning and enhanced capabilities

### Google Gemini
- **Gemini 2.0**: Gemini 2.0 Flash, Gemini 2.0 Flash Lite Preview
- **Gemini 2.5**: Gemini 2.5 Flash, Gemini 2.5 Flash Lite Preview, Gemini 2.5 Pro
- **Multimodal Support**: Text, image, and video understanding

### DeepSeek
- **DeepSeek V3**: Latest generation model with enhanced capabilities
- **DeepSeek Chat**: Conversational AI model
- **DeepSeek Reasoner**: Specialized reasoning model
- **DeepSeek R1**: Advanced reasoning model

### xAI Grok
- **Grok 2**: Advanced conversational AI
- **Grok 3**: Latest generation with improved performance
- **Grok 4**: Cutting-edge model with enhanced capabilities
- **Variants**: Beta, Mini, Fast versions available

## Features

- **Unified Interface**: OpenAI-compatible API reduces integration complexity
- **Multi-Modal**: Support for text, image, audio, and video processing
- **High Performance**: Global deployment with intelligent routing and load balancing
- **Enterprise Ready**: 24/7 support, custom model integration, and dedicated account management
- **Secure**: Full HTTPS encryption with DDoS protection

## Installation

### In Dify

1. Navigate to **Settings** → **Model Provider** in your Dify instance
2. Find **DeerAPI** in the provider list
3. Enter your DeerAPI API key
4. Configure the base URL if needed
5. Save the configuration

Your DeerAPI models will now be available in Dify's model selection.

## Configuration

### Getting API Key

1. Visit the DeerAPI console: https://api.deerapi.com/login
2. Register or log in to your account
3. Navigate to API keys section
4. Generate a new API key
5. Copy and securely store your API key

### Quick Start Example

```bash
curl https://api.deerapi.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Hello, DeerAPI!"}
    ],
    "temperature": 0.7
  }'
```

## Model Capabilities

| Model Family | Text Generation | Vision | Function Calling | Streaming | Reasoning |
|--------------|----------------|---------|------------------|-----------|-----------|
| OpenAI GPT-4 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Claude 3/3.5 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Gemini 2.x | ✅ | ✅ | ✅ | ✅ | ✅ |
| DeepSeek | ✅ | ❌ | ✅ | ✅ | ✅ |
| Grok | ✅ | ❌ | ✅ | ✅ | ✅ |

## Use Cases

- **Conversational AI**: Chatbots, virtual assistants, customer support
- **Content Generation**: Blog posts, articles, marketing copy
- **Code Generation**: Programming assistance, code review, debugging
- **Analysis & Reasoning**: Data analysis, problem-solving, research
- **Multimodal Tasks**: Image understanding, document processing

## Performance & Reliability

- **Global Infrastructure**: Multi-region deployment for low latency
- **Intelligent Routing**: Automatic routing to optimal endpoints
- **Load Balancing**: Distributed traffic management
- **High Availability**: 99.9% uptime SLA
- **Rate Limiting**: Configurable limits to prevent abuse

## Security

- **HTTPS Encryption**: All communications encrypted in transit
- **API Key Authentication**: Secure token-based access control
- **DDoS Protection**: Enterprise-grade protection via Cloudflare
- **Data Privacy**: No storage of user requests or responses

## Support

- **Documentation**: Comprehensive API documentation
- **24/7 Support**: Round-the-clock technical assistance
- **Community**: Developer forums and resources
- **Enterprise Support**: Dedicated account management for enterprise customers

## Contact

- **Website**: https://www.deerapi.com
- **Console**: https://api.deerapi.com
- **Email**: support@deerapi.com
- **WeChat**: cocolife1995

## Legal

- **Privacy Policy**: https://www.deerapi.com/privacy-policy
- **Terms of Service**: Available on the website
- **Compliance**: Adheres to international data protection regulations

---

**Note**: This service is not available to users in mainland China due to regulatory requirements.
