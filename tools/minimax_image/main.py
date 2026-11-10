from dify_plugin import DifyPluginEnv, Plugin

# H3-Image is not idempotent and may run up to 600s; do not retry, and wait longer than that.
# The HTTP call itself is allowed a 30s connect phase plus a 610s read phase (640s worst case,
# see utils.TIMEOUT), and image editing base64-encodes up to 16 reference images before the
# POST. The daemon connection has to outlive all of that: in serverless mode it is closed after
# MAX_REQUEST_TIMEOUT seconds without output, so a shorter budget would drop the result of a
# request that MiniMax did complete (and bill). 640s worst case + 60s of preparation headroom.
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=700))

if __name__ == "__main__":
    plugin.run()
