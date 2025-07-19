import traceback
import json
from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from .slidespeak_client import SlideSpeakClient
from .slidespeak_models import PresentationTemplate


class TemplateListerTool(Tool):
    """
    Tool for listing all available presentation templates from the SlideSpeak API
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Synchronous invoke method"""

        try:
            # Create client
            client = SlideSpeakClient.from_runtime_credentials(self.runtime)

            # Get presentation templates
            templates_data = client.get_presentation_templates()

            # Validate and create a list of PresentationTemplate objects
            templates = [PresentationTemplate(**data) for data in templates_data]

            # Collect all messages to yield at the end
            messages = []

            # Create a JSON message with the templates data wrapped in an object
            json_data = {"templates": templates_data, "count": len(templates_data)}
            messages.append(self.create_json_message(json_data))

            # Create a markdown text message with template information
            markdown_content = (
                f"# SlideSpeak Templates\n\nFound {len(templates)} templates.\n\n"
            )

            for template in templates:
                markdown_content += f"## {template.name}\n\n"
                markdown_content += "**Cover Image:**\n"
                markdown_content += (
                    f"![{template.name} Cover]({template.images.cover})\n\n"
                )
                markdown_content += "**Content Image:**\n"
                markdown_content += (
                    f"![{template.name} Content]({template.images.content})\n\n"
                )
                markdown_content += "---\n\n"

            messages.append(self.create_text_message(markdown_content))

            # Yield all messages after all downloads are complete
            for message in messages:
                yield message

        except Exception as e:
            traceback.print_exc()
            error_message = str(e)

            # Try to extract more detailed error information if possible
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_message = f"{error_message}\nDetails: {json.dumps(error_detail, indent=2)}"
                except Exception:
                    pass

            yield self.create_text_message(f"An error occurred: {error_message}")
