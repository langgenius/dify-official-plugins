import logging
import os
import sys
from pathlib import Path

# ensure unbuffered
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

os.chdir(Path(__file__).resolve().parent)
print("cwd", os.getcwd(), flush=True)
print("INSTALL_METHOD", os.environ.get("INSTALL_METHOD"), flush=True)
print("REMOTE_INSTALL_HOST", os.environ.get("REMOTE_INSTALL_HOST"), flush=True)
print("REMOTE_INSTALL_PORT", os.environ.get("REMOTE_INSTALL_PORT"), flush=True)
print("REMOTE_INSTALL_KEY set", bool(os.environ.get("REMOTE_INSTALL_KEY")), flush=True)

# load .env manually into environ before importing plugin (pydantic BaseSettings reads env)
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()
    print("loaded .env", flush=True)
    print("after load INSTALL_METHOD", os.environ.get("INSTALL_METHOD"), flush=True)
    print("after load KEY set", bool(os.environ.get("REMOTE_INSTALL_KEY")), flush=True)

from dify_plugin import Plugin, DifyPluginEnv

print("starting plugin remote debug...", flush=True)
plugin = Plugin(DifyPluginEnv())
plugin.run()
