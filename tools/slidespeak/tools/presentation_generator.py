import traceback
import json
from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from pydantic import ValidationError

from .slidespeak_models import PresentationRequest
from .slidespeak_client import SlideSpeakClient


class PresentationGeneratorTool(Tool):
    """
    Tool for generating presentations using the SlideSpeak API
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Synchronous invoke method"""

        # Pre-process document_uuids if it's a JSON string
        document_uuids_param = tool_parameters.get("document_uuids")
        if isinstance(document_uuids_param, str):
            try:
                loaded = json.loads(document_uuids_param)
                if isinstance(loaded, list):
                    tool_parameters["document_uuids"] = loaded
                else:
                    yield self.create_text_message(
                        "Error: document_uuids must be a JSON array of strings"
                    )
                    return
            except json.JSONDecodeError:
                yield self.create_text_message(
                    "Error: document_uuids must be a valid JSON string"
                )
                return
        elif document_uuids_param and not isinstance(document_uuids_param, list):
            yield self.create_text_message(
                "Error: document_uuids must be a list or JSON string"
            )
            return

        # Create a request object from tool parameters
        try:
            request = PresentationRequest(**tool_parameters)
        except ValidationError as e:
            yield self.create_text_message(f"Error: Invalid parameters - {e}")
            return

        if not request.plain_text and not request.document_uuids:
            yield self.create_text_message(
                "Error: Either plain_text or document_uuids is required"
            )
            return

        try:
            # Create client
            client = SlideSpeakClient.from_runtime_credentials(self.runtime)
            request_data = request.model_dump(exclude_none=True)
            download_url, presentation_bytes = client.generate_and_fetch_presentation(
                request_data=request_data
            )

            yield self.create_text_message(
                f"Presentation generated successfully. Download URL: {download_url}"
            )

            # Create JSON message with the response format
            response_data = {
                "task_id": client.last_task_id
                if hasattr(client, "last_task_id")
                else None,
                "task_status": "SUCCESS",
                "task_result": {"url": download_url},
                "task_info": {"url": download_url},
            }
            yield self.create_json_message(response_data)

            yield self.create_blob_message(
                blob=presentation_bytes,
                meta={
                    "mime_type": "application/pdf"
                    if request.response_format == "pdf"
                    else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                },
            )
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

            # Create JSON message for error case
            error_response = {
                "task_id": None,
                "task_status": "FAILURE",
                "task_result": None,
                "task_info": error_message,
            }
            yield self.create_json_message(error_response)

            yield self.create_text_message(f"An error occurred: {error_message}")
