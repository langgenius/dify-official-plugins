"""
AIHubMix Image Generation Plugin

This plugin provides image generation capabilities through various AI models
including GPT-Image, Flux, Imagen, Qwen, Doubao, and ERNIE iRAG.
"""

from dify_plugin import Plugin, DifyPluginEnv

# Initialize plugin with extended timeout for image generation tasks
# 4K image generation can take 3-5 minutes, so we set a 300-second timeout
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=300))

def main():
    """Entry point for the AIHubMix Image plugin."""
    plugin.run()

if __name__ == '__main__':
    main()
