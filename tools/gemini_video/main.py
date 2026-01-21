import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

from dify_plugin import Plugin, DifyPluginEnv


def setup_logging():
    """
    Dify is not capable to print log in plugin_daemon right now
    set up logging to volumes/plugin_daemon/plugin-logs to write down a plugin actual log
    as default, plugin_daemon is mounted in volumes/plugin_daemon
    so we just need to create a subdirectory called plugin-logs to store logs then write logs in it.
    """
    # directory path
    log_dir = '/app/storage/plugin-logs'

    # ensure directory exists
    os.makedirs(log_dir, exist_ok=True)

    # clear handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # log format
    # log will use utc time
    log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.INFO)

    # 2. rotate handler
    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, 'plugin_gemini_video.log'),
        when='D',
        interval=1,
        backupCount=15,
        encoding='utf-8',
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.INFO)

    logging.root.setLevel(logging.INFO)
    logging.root.addHandler(console_handler)
    logging.root.addHandler(file_handler)
    logging.info(f"log config initialized")

setup_logging()

logging.info("gemini video plugin initializing")
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))
logging.info("gemini video plugin initialized")

if __name__ == '__main__':
    try:
        plugin.run()
    except Exception as e:
        logging.error(f"gemini video plugin error：{str(e)}", exc_info=True)
    finally:
        logging.info("gemini video plugin finished")
