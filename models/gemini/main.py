import grpc.experimental.gevent
from dify_plugin import Plugin, DifyPluginEnv

grpc.experimental.gevent.init_gevent()

plugin = Plugin(DifyPluginEnv())

if __name__ == '__main__':
    plugin.run()
