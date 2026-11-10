from dify_plugin import DifyPluginEnv, Plugin

# H3-Image is not idempotent and may run up to 600s; do not retry, and wait longer than that.
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=620))

if __name__ == "__main__":
    plugin.run()
