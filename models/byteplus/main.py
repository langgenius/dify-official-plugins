from dify_plugin import Plugin, DifyPluginEnv
import logging

logging.basicConfig(level=logging.INFO)

plugin = Plugin(DifyPluginEnv())

if __name__ == '__main__':
    plugin.run()
