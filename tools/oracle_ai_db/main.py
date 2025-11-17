from dify_plugin import Plugin, DifyPluginEnv
# 正确初始化Plugin，使用DifyPluginEnv实例
plugin = Plugin(DifyPluginEnv())

if __name__ == '__main__':
    plugin.run()
