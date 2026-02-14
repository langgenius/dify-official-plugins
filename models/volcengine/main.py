from dify_plugin import Plugin

plugin = Plugin(
    model_providers=["provider.volcengine.VolcengineProvider"],
)

if __name__ == "__main__":
    plugin.run()
