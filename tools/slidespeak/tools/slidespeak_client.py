import time
from typing import Any, Dict, List
import httpx
import json
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from .slidespeak_models import TaskState


class SlideSpeakClient:
    """
    Centralized client for SlideSpeak API interactions
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.slidespeak.co/api/v1",
        timeout: float = 100.0,
        poll_interval: int = 2,
    ):
        """
        Initialize the SlideSpeak client

        Args:
            api_key: SlideSpeak API key
            base_url: Base URL for the API
            timeout: Request timeout in seconds
            poll_interval: Polling interval for task status checks
        """
        if not api_key:
            raise ToolProviderCredentialValidationError(
                "SlideSpeak API key is required"
            )

        self.base_url = base_url
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.headers = {"Content-Type": "application/json", "X-API-Key": api_key}

    def _log_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Any = None,
        files: Any = None,
    ):
        """Log request details"""
        print("\n=== REQUEST ===")
        print(f"Method: {method}")
        print(f"URL: {url}")
        print(f"Headers: {json.dumps(headers, indent=2)}")
        if body:
            print(f"Body: {json.dumps(body, indent=2)}")
        if files:
            print(f"Files: {files}")
        print("================\n")

    def _log_response(self, response: httpx.Response):
        """Log response details"""
        print("\n=== RESPONSE ===")
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        try:
            response_json = response.json()
            print(f"Body: {json.dumps(response_json, indent=2)}")
        except Exception:
            print(f"Body (raw): {response.text}")
        print("=================\n")

    @classmethod
    def from_runtime_credentials(cls, runtime, **kwargs):
        """
        Create client from Dify runtime credentials

        Args:
            runtime: Dify runtime object with credentials
            **kwargs: Additional configuration options
        """
        if not runtime or not runtime.credentials:
            raise ToolProviderCredentialValidationError(
                "Tool runtime or credentials are missing"
            )

        api_key = runtime.credentials.get("slidespeak_api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError("SlideSpeak API key is missing")

        return cls(api_key=api_key, **kwargs)

    def generate_presentation(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a presentation using the standard API endpoint

        Args:
            request_data: Request payload for presentation generation

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/presentation/generate"
        self._log_request("POST", url, self.headers, request_data)

        with httpx.Client() as client:
            response = client.post(
                url, headers=self.headers, json=request_data, timeout=self.timeout
            )
            self._log_response(response)
            response.raise_for_status()
            return response.json()

    def generate_presentation_slide_by_slide(
        self, request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate a presentation using the slide-by-slide API endpoint

        Args:
            request_data: Request payload for slide-by-slide generation

        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}/presentation/generate/slide-by-slide"
        self._log_request("POST", url, self.headers, request_data)

        with httpx.Client() as client:
            response = client.post(
                url, headers=self.headers, json=request_data, timeout=self.timeout
            )
            self._log_response(response)
            response.raise_for_status()
            return response.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the status of a task

        Args:
            task_id: Task ID to check

        Returns:
            Task status response as dictionary
        """
        url = f"{self.base_url}/task_status/{task_id}"
        self._log_request("GET", url, self.headers)

        with httpx.Client() as client:
            response = client.get(url, headers=self.headers, timeout=self.timeout)
            self._log_response(response)
            response.raise_for_status()
            return response.json()

    def get_presentation_templates(self) -> List[Dict[str, Any]]:
        """
        Get all available presentation templates

        Returns:
            A list of presentation templates

        Raises:
            Exception: If the request fails
        """
        url = f"{self.base_url}/presentation/templates"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.headers["X-API-Key"],
        }

        self._log_request("GET", url, headers)
        with httpx.Client() as client:
            response = client.get(url, headers=headers)
            self._log_response(response)

        response.raise_for_status()
        return response.json()

    def wait_for_completion(self, task_id: str) -> str:
        """
        Wait for task completion and return download URL

        Args:
            task_id: Task ID to monitor

        Returns:
            Download URL when task completes successfully

        Raises:
            Exception: If task fails
        """
        while True:
            status = self.get_task_status(task_id)
            task_status = TaskState(status["task_status"])

            if task_status == TaskState.SUCCESS:
                return status["task_result"]["url"]

            if task_status == TaskState.FAILURE:
                raise Exception(f"Task failed with status: {task_status.value}")

            time.sleep(self.poll_interval)

    def fetch_presentation(self, download_url: str) -> bytes:
        """
        Fetch the presentation file from the download URL

        Args:
            download_url: URL to download the presentation from

        Returns:
            Presentation file content as bytes
        """
        self._log_request("GET", download_url, {})

        with httpx.Client() as client:
            response = client.get(download_url, timeout=self.timeout)
            print("\n=== FETCH RESPONSE ===")
            print(f"Status Code: {response.status_code}")
            print(f"Headers: {dict(response.headers)}")
            print(f"Content Length: {len(response.content)} bytes")
            print("=======================\n")
            response.raise_for_status()
            return response.content

    def generate_and_fetch_presentation(
        self, request_data: Dict[str, Any]
    ) -> tuple[str, bytes]:
        """
        Complete workflow: generate presentation and fetch the file

        Args:
            request_data: Request payload for presentation generation

        Returns:
            Tuple of (download_url, presentation_bytes)
        """
        result = self.generate_presentation(request_data)

        # Handle synchronous response (direct URL)
        if isinstance(result, dict):
            if "url" in result:
                download_url = result["url"]
                presentation_bytes = self.fetch_presentation(download_url)
                return download_url, presentation_bytes

            if result.get("task_result") and isinstance(result["task_result"], dict):
                if "url" in result["task_result"]:
                    download_url = result["task_result"]["url"]
                    presentation_bytes = self.fetch_presentation(download_url)
                    return download_url, presentation_bytes

        # Handle asynchronous response (task ID)
        task_id = result["task_id"]
        download_url = self.wait_for_completion(task_id)
        presentation_bytes = self.fetch_presentation(download_url)
        return download_url, presentation_bytes

    def generate_and_fetch_presentation_slide_by_slide(
        self, request_data: Dict[str, Any]
    ) -> tuple[str, bytes]:
        """
        Complete workflow: generate slide-by-slide presentation and fetch the file

        Args:
            request_data: Request payload for slide-by-slide generation

        Returns:
            Tuple of (download_url, presentation_bytes)
        """
        result = self.generate_presentation_slide_by_slide(request_data)
        task_id = result["task_id"]
        download_url = self.wait_for_completion(task_id)
        presentation_bytes = self.fetch_presentation(download_url)
        return download_url, presentation_bytes

    def upload_document(self, file_bytes: bytes, filename: str):
        """Upload a document file to SlideSpeak. Returns JSON response containing task_id."""
        url = f"{self.base_url}/document/upload"
        upload_headers = {"X-API-Key": self.headers["X-API-Key"]}
        files_info = {"file": (filename, f"<{len(file_bytes)} bytes>")}

        self._log_request("POST", url, upload_headers, files=files_info)

        with httpx.Client() as client:
            response = client.post(
                url,
                headers=upload_headers,
                files={"file": (filename, file_bytes)},
                timeout=self.timeout,
            )
            self._log_response(response)
            response.raise_for_status()
            return response.json()

    def upload_document_and_get_uuid(self, file_bytes: bytes, filename: str) -> str:
        """Upload document and wait for processing to complete. Returns the resulting document UUID."""
        result = self.upload_document(file_bytes, filename)
        task_id = result["task_id"]

        while True:
            status = self.get_task_status(task_id)
            task_status = TaskState(status["task_status"])

            if task_status == TaskState.SUCCESS:
                # According to API docs the UUID is provided either in task_result or task_info
                return status.get("task_result") or status.get("task_info")

            if task_status == TaskState.FAILURE:
                raise Exception(
                    f"Document upload failed with status: {task_status.value}"
                )

            time.sleep(self.poll_interval)
