import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

from dify_plugin import Plugin, DifyPluginEnv


def setup_logging():
    """
    Configure logging for the plugin.

    Note: Dify plugin daemon cannot print logs directly.
    Logs are written to /app/storage/plugin-logs by default.
    If the directory is not accessible (e.g., CI environment),
    file logging is automatically skipped and console logging continues.
    """
    # directory path
    log_dir = '/app/storage/plugin-logs'

    # clear existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # log format
    log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 1. console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.INFO)

    # 2. file handler (auto-fallback on permission error)
    file_handler = None
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            filename=os.path.join(log_dir, 'plugin_gemini_video.log'),
            when='D',
            interval=1,
            backupCount=15,
            encoding='utf-8',
        )
        file_handler.setFormatter(log_format)
        file_handler.setLevel(logging.INFO)
    except (PermissionError, OSError):
        # Skip file logging if directory is not accessible
        # This allows the plugin to run in CI environments
        pass

    # configure root logger
    logging.root.setLevel(logging.INFO)
    logging.root.addHandler(console_handler)

    if file_handler:
        logging.root.addHandler(file_handler)
        logging.info("file logging enabled")
    else:
        logging.info("file logging disabled (console only)")

setup_logging()

logging.info("gemini video plugin initializing")
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))
logging.info("gemini video plugin initialized")

if __name__ == '__main__':
    try:
        plugin.run()
    except Exception as e:
        logging.error(f"gemini video plugin error: {str(e)}", exc_info=True)
    finally:
        logging.info("gemini video plugin finished")
