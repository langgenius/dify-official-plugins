"""AIHubMix image plugin.

Two tools — generate and edit — that talk to the gateway's unified image endpoint and
discover each model's parameters from its published schema at call time.
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
