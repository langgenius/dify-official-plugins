import sys

sys.path.append("../..")  # ENSURE THE SOURCE CODE IS FOUND

from dify_plugin import DifyPluginEnv, Plugin

plugin = Plugin(DifyPluginEnv())

if __name__ == "__main__":
    plugin.run()
