import json
import traceback
import re
from typing import Mapping
from werkzeug import Request, Response
from dify_plugin import Endpoint
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def convert_markdown_to_mrkdwn(text: str) -> str:
    """
    Convert standard markdown to Slack mrkdwn format.
    """
    if not text:
        return text
    
    # Convert bold: **text** to *text*
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
    
    # Convert italic: *text* to _text_, but avoid conflicts with bold
    # First protect already converted bold
    bold_placeholder = "___BOLD_PLACEHOLDER___"
    bold_parts = re.findall(r'\*(.*?)\*', text)
    for i, part in enumerate(bold_parts):
        text = text.replace(f'*{part}*', f'{bold_placeholder}{i}', 1)
    
    # Now convert remaining *text* to _text_
    text = re.sub(r'\*(.*?)\*', r'_\1_', text)
    
    # Restore bold parts
    for i, part in enumerate(bold_parts):
        text = text.replace(f'{bold_placeholder}{i}', f'*{part}*')
    
    # Convert strikethrough: ~~text~~ to ~text~
    text = re.sub(r'~~(.*?)~~', r'~\1~', text)
    
    # Convert inline code: `code` stays the same
    # Already compatible with Slack
    
    # Convert links: [text](url) to <url|text>
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<\2|\1>', text)
    
    # Convert code blocks: ```code``` to ```code``` (mostly compatible)
    # Slack supports code blocks with ```
    
    # Convert unordered lists: - item or * item to • item
    text = re.sub(r'^[\s]*[-*]\s+(.*)$', r'• \1', text, flags=re.MULTILINE)
    
    # Convert numbered lists: 1. item to 1. item (keep as is, but ensure proper formatting)
    text = re.sub(r'^[\s]*(\d+)\.\s+(.*)$', r'\1. \2', text, flags=re.MULTILINE)
    
    return text


class SlackEndpoint(Endpoint):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        """
        Invokes the endpoint with the given request.
        """
        retry_num = r.headers.get("X-Slack-Retry-Num")
        if (not settings.get("allow_retry") and (r.headers.get("X-Slack-Retry-Reason") == "http_timeout" or ((retry_num is not None and int(retry_num) > 0)))):
            return Response(status=200, response="ok")
        data = r.get_json()

        # Handle Slack URL verification challenge
        if data.get("type") == "url_verification":
            return Response(
                response=json.dumps({"challenge": data.get("challenge")}),
                status=200,
                content_type="application/json"
            )
        
        if (data.get("type") == "event_callback"):
            event = data.get("event")
            if (event.get("type") == "app_mention"):
                message = event.get("text", "")
                if message.startswith("<@"):
                    message = message.split("> ", 1)[1] if "> " in message else message
                    channel = event.get("channel", "")
                    token = settings.get("bot_token")
                    client = WebClient(token=token)
                    try: 
                        response = self.session.app.chat.invoke(
                            app_id=settings["app"]["app_id"],
                            query=message,
                            inputs={},
                            response_mode="blocking",
                        )
                        try:
                            answer = response.get("answer", "")
                            formatted_answer = convert_markdown_to_mrkdwn(answer)
                            
                            # Create proper mrkdwn block structure
                            blocks = [{
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": formatted_answer
                                }
                            }]
                            
                            result = client.chat_postMessage(
                                channel=channel,
                                text=formatted_answer,  # Fallback text
                                blocks=blocks,
                                mrkdwn=True
                            )
                            return Response(
                                status=200,
                                response=json.dumps(result),
                                content_type="application/json"
                            )
                        except SlackApiError as e:
                            raise e
                    except Exception as e:
                        err = traceback.format_exc()
                        return Response(
                            status=200,
                            response="Sorry, I'm having trouble processing your request. Please try again later." + str(err),
                            content_type="text/plain",
                        )
                else:
                    return Response(status=200, response="ok")
            else:
                return Response(status=200, response="ok")
        else:
            return Response(status=200, response="ok")
