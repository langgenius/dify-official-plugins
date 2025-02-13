from tools.slack_webhook import SlackWebhookTool
from dify_plugin import ToolProvider


class SlackProvider(ToolProvider):
    tool_parameters = [
        {
            "name": "webhook_url",
            "type": "string",
            "required": True,
            "description": "Slack webhook URL for sending messages"
        }
    ]

    def _validate_credentials(self, credentials: dict) -> None:
        if 'webhook_url' not in credentials:
            raise ValueError("webhook_url is required in credentials")
        webhook_url = credentials['webhook_url']
        if not isinstance(webhook_url, str) or not webhook_url.startswith('https://hooks.slack.com/'):
            raise ValueError("Invalid Slack webhook URL format")
