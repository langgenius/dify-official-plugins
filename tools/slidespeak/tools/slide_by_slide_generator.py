import traceback
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Generator, Union
import httpx
from pydantic import ConfigDict
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool


class SlideBySlideGeneratorTool(Tool):
    """
    Tool for generating presentations slide by slide using the SlideSpeak API
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    headers: Optional[dict[str, str]]
    base_url: Optional[str]
    timeout: Optional[float]
    poll_interval: Optional[int]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Default configuration values
        self.base_url = "https://api.slidespeak.co/api/v1"
        self.timeout = 60.0
        self.poll_interval = 2

    def _setup_api_credentials(self):
        """Set up API credentials from runtime configuration"""
        if not self.runtime or not self.runtime.credentials:
            raise ToolProviderCredentialValidationError("Tool runtime or credentials are missing")
        api_key = self.runtime.credentials.get("slidespeak_api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError("SlideSpeak API key is missing")
        self.headers = {"Content-Type": "application/json", "X-API-Key": api_key}

    class TaskState(Enum):
        FAILURE = "FAILURE"
        REVOKED = "REVOKED"
        SUCCESS = "SUCCESS"
        PENDING = "PENDING"
        RECEIVED = "RECEIVED"
        STARTED = "STARTED"
        SENT = "SENT"

    @dataclass
    class SlideDefinition:
        title: str
        layout: str
        item_amount: int
        content_description: str

    @dataclass
    class SlideBySlideRequest:
        slides: List[Dict[str, Union[str, int]]]
        template: str
        language: Optional[str] = None
        fetch_images: Optional[bool] = None

    def _generate_presentation_slide_by_slide(
        self, client: httpx.Client, request: SlideBySlideRequest
    ) -> dict[str, Any]:
        """Generate a new presentation slide by slide synchronously"""
        # Filter out None values to avoid sending unnecessary parameters
        request_dict = {k: v for k, v in asdict(request).items() if v is not None}
        
        response = client.post(
            f"{self.base_url}/presentation/generate/slide-by-slide", 
            headers=self.headers, 
            json=request_dict,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def _get_task_status(self, client: httpx.Client, task_id: str) -> dict[str, Any]:
        """Get the status of a task synchronously"""
        response = client.get(
            f"{self.base_url}/task_status/{task_id}",
            headers=self.headers,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def _wait_for_completion(self, client: httpx.Client, task_id: str) -> str:
        """Wait for task completion and return download URL"""
        import time
        while True:
            status = self._get_task_status(client, task_id)
            task_status = self.TaskState(status["task_status"])
            if task_status == self.TaskState.SUCCESS:
                return status["task_result"]["url"]
            if task_status in [self.TaskState.FAILURE, self.TaskState.REVOKED]:
                raise Exception(f"Task failed with status: {task_status.value}")
            time.sleep(self.poll_interval)

    def _generate_presentation_content(self, **kwargs) -> str:
        """Generate presentation content and return the download URL"""
        with httpx.Client() as client:
            request = self.SlideBySlideRequest(**kwargs)
            result = self._generate_presentation_slide_by_slide(client, request)
            task_id = result["task_id"]
            download_url = self._wait_for_completion(client, task_id)
            return download_url

    def _fetch_presentation(self, client: httpx.Client, download_url: str) -> bytes:
        """Fetch the presentation file from the download URL"""
        response = client.get(download_url, timeout=self.timeout)
        response.raise_for_status()
        return response.content

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Synchronous invoke method"""
        # Extract required parameters
        slides_str = tool_parameters.get("slides")
        if not slides_str:
            yield self.create_text_message("Error: slides is required")
            return
            
        # Convert slides from JSON string to list of dictionaries
        try:
            slides = json.loads(slides_str)
            if not isinstance(slides, list):
                yield self.create_text_message("Error: slides must be a JSON array")
                return
                
            # Validate each slide has the required keys and convert item_amount to integer
            for i, slide in enumerate(slides):
                if not isinstance(slide, dict):
                    yield self.create_text_message(f"Error: slide {i+1} must be a dictionary")
                    return
                required_keys = ["title", "layout", "item_amount", "content_description"]
                missing_keys = [key for key in required_keys if key not in slide]
                if missing_keys:
                    yield self.create_text_message(f"Error: slide {i+1} is missing required keys: {', '.join(missing_keys)}")
                    return
                
                # Convert item_amount to integer if it's a string
                if isinstance(slide["item_amount"], str):
                    try:
                        slide["item_amount"] = int(slide["item_amount"])
                    except ValueError:
                        yield self.create_text_message(f"Error: item_amount in slide {i+1} must be a valid integer")
                        return
        except json.JSONDecodeError:
            yield self.create_text_message("Error: slides must be a valid JSON string")
            return
            
        template = tool_parameters.get("template")
        if not template:
            yield self.create_text_message("Error: template is required")
            return
        
        # Extract optional parameters
        language = tool_parameters.get("language")
        fetch_images = tool_parameters.get("fetch_images")
        
        # Set up API credentials
        self._setup_api_credentials()
        
        try:
            # Prepare kwargs
            kwargs = {
                "slides": slides,
                "template": template
            }
            
            # Add optional parameters only if they're not None
            if language is not None and language != "":
                kwargs["language"] = language
            if fetch_images is not None:
                kwargs["fetch_images"] = fetch_images

            print(f"Generating presentation with parameters: {kwargs}")
            
            download_url = self._generate_presentation_content(**kwargs)
            with httpx.Client() as client:
                presentation_bytes = self._fetch_presentation(client, download_url)
            
            print(f"Presentation generated successfully: {download_url}")
            yield self.create_text_message(f"Presentation generated successfully. Download URL: {download_url}")
            yield self.create_blob_message(
                blob=presentation_bytes,
                meta={"mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
            )
        except Exception as e:
            traceback.print_exc()
            error_message = str(e)
            
            # Try to extract more detailed error information if possible
            if isinstance(e, httpx.HTTPStatusError) and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_message = f"{error_message}\nDetails: {json.dumps(error_detail, indent=2)}"
                except:
                    pass
                    
            yield self.create_text_message(f"An error occurred: {error_message}") 