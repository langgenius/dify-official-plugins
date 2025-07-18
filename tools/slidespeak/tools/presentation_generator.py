import traceback
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional, Generator
import httpx
from pydantic import ConfigDict
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool


class PresentationGeneratorTool(Tool):
    """
    Tool for generating presentations using the SlideSpeak API
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
    class PresentationRequest:
        plain_text: str
        length: int  # Required
        template: str  # Required
        language: Optional[str] = None
        fetch_images: Optional[bool] = None
        tone: Optional[str] = None
        verbosity: Optional[str] = None
        custom_user_instructions: Optional[str] = None
        include_cover: Optional[bool] = None
        include_table_of_contents: Optional[bool] = None
        use_branding_logo: Optional[bool] = None
        use_branding_color: Optional[bool] = None

    def _generate_presentation(
        self, client: httpx.Client, request: PresentationRequest
    ) -> dict[str, Any]:
        """Generate a new presentation synchronously"""
        # Filter out None values to avoid sending unnecessary parameters
        request_dict = {k: v for k, v in asdict(request).items() if v is not None}
        
        response = client.post(
            f"{self.base_url}/presentation/generate", 
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
            request = self.PresentationRequest(**kwargs)
            result = self._generate_presentation(client, request)
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
        plain_text = tool_parameters.get("plain_text")
        if not plain_text:
            yield self.create_text_message("Error: plain_text is required")
            return
            
        length = tool_parameters.get("length")
        if length is None:
            yield self.create_text_message("Error: length is required")
            return
            
        template = tool_parameters.get("template")
        if not template:
            yield self.create_text_message("Error: template is required")
            return
        
        # Extract optional parameters
        language = tool_parameters.get("language")
        fetch_images = tool_parameters.get("fetch_images")
        tone = tool_parameters.get("tone")
        verbosity = tool_parameters.get("verbosity")
        custom_user_instructions = tool_parameters.get("custom_user_instructions")
        include_cover = tool_parameters.get("include_cover")
        include_table_of_contents = tool_parameters.get("include_table_of_contents")
        use_branding_logo = tool_parameters.get("use_branding_logo")
        use_branding_color = tool_parameters.get("use_branding_color")
        
        # Set up API credentials
        self._setup_api_credentials()
        
        try:
            # Prepare kwargs
            kwargs = {
                "plain_text": plain_text,
                "length": length,
                "template": template
            }
            
            # Add optional parameters only if they're not None
            if language is not None and language != "":
                kwargs["language"] = language
            if fetch_images is not None:
                kwargs["fetch_images"] = fetch_images
            if tone is not None and tone != "":
                kwargs["tone"] = tone
            if verbosity is not None and verbosity != "":
                kwargs["verbosity"] = verbosity
            if custom_user_instructions is not None and custom_user_instructions != "":
                kwargs["custom_user_instructions"] = custom_user_instructions
            if include_cover is not None:
                kwargs["include_cover"] = include_cover
            if include_table_of_contents is not None:
                kwargs["include_table_of_contents"] = include_table_of_contents
            if use_branding_logo is not None:
                kwargs["use_branding_logo"] = use_branding_logo
            if use_branding_color is not None:
                kwargs["use_branding_color"] = use_branding_color

            print(kwargs)
            
            download_url = self._generate_presentation_content(**kwargs)
            with httpx.Client() as client:
                presentation_bytes = self._fetch_presentation(client, download_url)
            
            print(download_url)
            yield self.create_text_message(download_url)
            yield self.create_blob_message(
                blob=presentation_bytes,
                meta={"mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
            )
        except Exception as e:
            traceback.print_exc()
            yield self.create_text_message(f"An error occurred: {str(e)}")
