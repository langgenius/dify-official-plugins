# Overview
HPC-AI provides OpenAI-compatible model APIs for production inference workloads. This plugin adds HPC-AI as a Dify model provider with predefined chat models.

# Configuration
After installation, get an API key from [HPC-AI](https://www.hpc-ai.com/doc/docs/quickstart/) and configure it in **Settings -> Model Provider**.

The plugin uses the fixed OpenAI-compatible endpoint:

```text
https://api.hpc-ai.com/inference/v1
```

## Supported Models

- `minimax/minimax-m2.5`
- `moonshotai/kimi-k2.5`
- `zai-org/glm-5.1`
