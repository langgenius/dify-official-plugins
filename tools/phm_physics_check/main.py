from dify_plugin import DifyPluginEnv, Plugin

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_SIZE=10 * 1024 * 1024))

if __name__ == "__main__":
    plugin.run()
