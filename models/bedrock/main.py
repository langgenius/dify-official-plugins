from dify_plugin import Plugin, DifyPluginEnv
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))

if __name__ == '__main__':
    plugin.run()
