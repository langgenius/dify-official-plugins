import logging

from dify_plugin import DifyPluginEnv, Plugin

logging.basicConfig(level=logging.INFO)

plugin = Plugin(DifyPluginEnv())

if __name__ == "__main__":
    plugin.run()
