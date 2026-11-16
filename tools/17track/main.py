from dify_plugin import DifyPlugin, DifyPluginEnv

plugin = DifyPlugin(env=DifyPluginEnv(max_request_threads=20))

if __name__ == "__main__":
    plugin.run()
