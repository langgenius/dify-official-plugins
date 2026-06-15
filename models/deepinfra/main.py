from dify_plugin import Plugin, DifyPluginEnv
import logging
import os
import socket

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

_host = socket.gethostname()
_env_count = len([k for k in os.environ if not k.startswith("_")])
_logger.info("deepinfra plugin | host=%s | configured_env_vars=%d", _host, _env_count)

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))

if __name__ == "__main__":
    plugin.run()