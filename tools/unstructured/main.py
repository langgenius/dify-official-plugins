from dify_plugin import Plugin, DifyPluginEnv

# 10-minute Transform job deadline plus upload + download transfer phases (120s each) and MCP handshake headroom.
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=900))

if __name__ == "__main__":
    plugin.run()
