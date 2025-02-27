from typing import Any, Generator, Optional, Dict
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
import time

SILICONFLOW_VIDEO_CREATE_ENDPOINT = "https://api.siliconflow.cn/v1/video/submit"
SILICONFLOW_VIDEO_STATUS_ENDPOINT = "https://api.siliconflow.cn/v1/video/status"

VIDEO_MODELS = {
    "LTX-Video": "Lightricks/LTX-Video",
    "HunyuanVideo": "tencent/HunyuanVideo",
    "mochi-1-preview":"genmo/mochi-1-preview" 
}


class VideoTool(Tool):
    def _send_generation_request(self, payload: dict, headers: dict) -> tuple[bool, str, str]:
        """Send video generation request
        Returns:
            tuple: (success status, requestId, error message)
        """
        response = requests.post(SILICONFLOW_VIDEO_CREATE_ENDPOINT, json=payload, headers=headers)
        if response.status_code != 200:
            return False, "", f"Fail to submit video generation request: {response.text}"
        
        res = response.json()
        request_id = res.get("requestId")
        if not request_id:
            return False, "", "Failed to get requestId"
        
        return True, request_id, ""

    def _check_generation_status(self, request_id: str, headers: dict) -> tuple[str, str, str]:
        """Check video generation status
        Returns:
            tuple: (status, video_url, error message)
        """
        status_payload = {"requestId": request_id}
        status_response = requests.post(
            SILICONFLOW_VIDEO_STATUS_ENDPOINT,
            json=status_payload,
            headers=headers
        )
        
        if status_response.status_code != 200:
            return "Error", "", f"Got Error Response:{status_response.text}"
        
        status_data = status_response.json()
        status = status_data.get("status")
        
        if status == "Succeed":
            videos = status_data.get("results", {}).get("videos", [])
            if videos and len(videos) > 0:
                return status, videos[0].get("url"), ""
            return status, "", "No video URL found"
        
        elif status == "InProgress":
            return status, "", ""
        
        else:
            reason = status_data.get("reason", "Contact contact@siliconflow.cn for Support.")
            return status, "", f"Fail to generate video: {status}, reason: {reason}"

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Main invocation logic"""
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.runtime.credentials['siliconFlow_api_key']}",
        }
        
        # Prepare request parameters
        model = tool_parameters.get("model", "Lightricks/LTX-Video")
        video_model = VIDEO_MODELS.get(model)
        payload = {
            "model": video_model,
            "prompt": tool_parameters.get("prompt"),
            "seed": tool_parameters.get("seed"),
        }
        
        try:
            # Send generation request
            success, request_id, error = self._send_generation_request(payload, headers)
            if not success:
                yield self.create_text_message(error)
                return
            
            # Poll for status
            max_retries = 60
            interval = 5
            
            for _ in range(max_retries):
                try:
                    status, video_url, error = self._check_generation_status(request_id, headers)
                    
                    if status == "Succeed":
                        if video_url:
                            yield self.create_image_message(video_url)
                        else:
                            yield self.create_text_message(error)
                        return
                    
                    elif status == "InProgress":
                        time.sleep(interval)
                        continue
                    
                    else:
                        yield self.create_text_message(error)
                        return
                    
                except Exception as e:
                    yield self.create_text_message(f"Fail to check video status: {str(e)}")
                    return
            
            yield self.create_text_message(f"Reach max retries {max_retries}, video generation may still be in progress")
            
        except Exception as e:
            yield self.create_text_message(f"Failed to send request: {str(e)}")
