from dify_plugin import Plugin

plugin = Plugin(
    model_providers=["provider.volcengine_ark.VolcengineArkProvider"],
)

if __name__ == "__main__":
    plugin.run()
