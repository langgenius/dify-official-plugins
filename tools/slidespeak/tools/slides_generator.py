import traceback
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional, Generator
import httpx
from pydantic import ConfigDict
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool


class SlidesGeneratorTool(Tool):
    """
    Tool for generating presentations using the SlideSpeak API
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    headers: Optional[dict[str, str]] = None
    base_url: Optional[str] = None
    timeout: Optional[float] = None
    poll_interval: Optional[int] = None

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
        length: Optional[int] = None
        theme: Optional[str] = None

    def _generate_presentation(
        self, client: httpx.Client, request: PresentationRequest
    ) -> dict[str, Any]:
        """Generate a new presentation synchronously"""
        response = client.post(
            f"{self.base_url}/presentation/generate", 
            headers=self.headers, 
            json=asdict(request),
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

    def _generate_slides(self, plain_text: str, length: Optional[int], theme: Optional[str]) -> str:
        """Generate slides and return the download URL"""
        with httpx.Client() as client:
            request = self.PresentationRequest(plain_text=plain_text, length=length, theme=theme)
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
        plain_text = tool_parameters.get("plain_text", "")
        length = tool_parameters.get("length")
        theme = tool_parameters.get("theme")
        if not self.runtime or not self.runtime.credentials:
            raise ToolProviderCredentialValidationError("Tool runtime or credentials are missing")
        api_key = self.runtime.credentials.get("slidespeak_api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError("SlideSpeak API key is missing")
        self.headers = {"Content-Type": "application/json", "X-API-Key": api_key}
        self.base_url = "https://api.slidespeak.co/api/v1"
        self.timeout = 30.0
        self.poll_interval = 2
        try:
            download_url = self._generate_slides(plain_text, length, theme)
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
