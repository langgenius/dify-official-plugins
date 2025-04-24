from typing import Any, Generator, Optional, Dict, List, Union
import requests
import base64
import time
import os
import traceback
import json
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
import io
import tempfile
from pathlib import Path

SILICONFLOW_VIDEO_CREATE_ENDPOINT = "https://api.siliconflow.cn/v1/video/submit"
SILICONFLOW_VIDEO_STATUS_ENDPOINT = "https://api.siliconflow.cn/v1/video/status"

# Request timeout settings (seconds)
REQUEST_TIMEOUT = 60  # API request timeout

# Text-to-video model list
T2V_MODELS = [
    "tencent/HunyuanVideo",
    "tencent/HunyuanVideo-HD",
    "Wan-AI/Wan2.1-T2V-14B",
    "Wan-AI/Wan2.1-T2V-14B-Turbo"
]

os.environ["SILICONFLOW_API_KEY"] = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")

def text_to_video(
    prompt: str,
    model: str = "tencent/hunyuan-video",
    image_size: str = "1280x720",
    seed: Optional[int] = None,
    negative_prompt: Optional[str] = None,
) -> dict:
    """
    Generate a video from a text prompt using SiliconFlow API.
    
    Args:
        prompt: Text description of the video to generate
        model: Model to use for generation
        image_size: Resolution of the output video
        seed: Seed for generation (optional)
        negative_prompt: Negative prompt (optional)
        
    Returns:
        dict: A dictionary containing the result with either a video URL or an error message
    """
    # Check if API key is available
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "message": "SILICONFLOW_API_KEY not found in environment variables"
        }
    
    # Set up API request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Prepare API parameters
    payload = {
        "prompt": prompt,
        "model": model,
        "size": image_size,
    }
    
    # Add optional parameters if provided
    if seed is not None:
        payload["seed"] = seed
    
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt
    
    try:
        # Make the API request
        response = requests.post(
            "https://api.siliconflow.cn/v1/videos/generations",
            headers=headers,
            json=payload,
            timeout=60  # Initial request timeout
        )
        
        # Check for errors in the initial response
        if response.status_code != 200:
            try:
                error_detail = response.json()
                error_message = error_detail.get("error", {}).get("message", "Unknown error")
                return {
                    "status": "error", 
                    "message": f"API error: {error_message}"
                }
            except:
                return {
                    "status": "error", 
                    "message": f"API error: {response.status_code} - {response.text}"
                }
        
        # Get the task ID from the response
        task_data = response.json()
        task_id = task_data.get("id")
        
        if not task_id:
            return {
                "status": "error",
                "message": "No task ID returned from API"
            }
        
        # Poll for the task result
        max_attempts = 30
        attempts = 0
        
        while attempts < max_attempts:
            try:
                check_response = requests.get(
                    f"https://api.siliconflow.cn/v1/videos/generations/{task_id}",
                    headers=headers,
                    timeout=10
                )
                
                if check_response.status_code != 200:
                    attempts += 1
                    time.sleep(5)
                    continue
                
                result = check_response.json()
                status = result.get("status")
                
                if status == "succeeded":
                    # Task completed successfully
                    video_url = result.get("video", {}).get("url")
                    
                    if not video_url:
                        return {
                            "status": "error",
                            "message": "No video URL in the completed task"
                        }
                    
                    # Return the video URL
                    return {
                        "status": "success",
                        "video_url": video_url
                    }
                    
                elif status == "failed":
                    # Task failed
                    error_message = result.get("error", {}).get("message", "Unknown error")
                    return {
                        "status": "error",
                        "message": f"Video generation failed: {error_message}"
                    }
                    
                # Task still in progress, continue polling
                attempts += 1
                time.sleep(5)
                
            except Exception as e:
                attempts += 1
                time.sleep(5)
        
        # If we've exhausted our polling attempts
        return {
            "status": "error",
            "message": "Timeout waiting for video generation to complete"
        }
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error: {str(e)}"
        }

class TextToVideoTool(Tool):
    def _log_message(self, message):
        """Log message with timestamp"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        return f"[{timestamp}] {message}"

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Main invocation logic"""
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.runtime.credentials['siliconFlow_api_key']}",
        }
        
        # Get model and basic parameters
        model = tool_parameters.get("model")
        prompt = tool_parameters.get("prompt")
        
        # Basic parameter check
        if not model:
            yield self.create_text_message("Error: Please select a video generation model")
            return
        
        if not prompt:
            yield self.create_text_message("Error: Please enter a prompt")
            return
        
        # Output initial log
        yield self.create_text_message(self._log_message(f"Starting text-to-video generation with model: {model}"))
        
        # Get seed parameter
        seed = tool_parameters.get("seed")
        
        # Prepare basic payload
        payload = {
            "model": model,
            "prompt": prompt,
        }
        
        # Add seed if provided
        if seed is not None:
            payload["seed"] = seed
            
        # Process model-specific parameters
        if model.startswith("Wan-AI/"):
            # Text-to-video needs image size
            image_size = tool_parameters.get("image_size", "1280x720")
            negative_prompt = tool_parameters.get("negative_prompt")
            
            # Set image size
            payload["image_size"] = image_size
            
            # Add negative prompt if provided
            if negative_prompt:
                payload["negative_prompt"] = negative_prompt
        
        try:
            # Send generation request
            yield self.create_text_message(self._log_message("Sending video generation request..."))
            
            # Prepare the request
            try:
                response = requests.post(
                    SILICONFLOW_VIDEO_CREATE_ENDPOINT, 
                    json=payload, 
                    headers=headers,
                    timeout=REQUEST_TIMEOUT
                )
                
                debug_info = f"Response received: Status code={response.status_code}, Response size={len(response.text)} bytes"
                yield self.create_text_message(self._log_message(debug_info))
                
                if response.status_code != 200:
                    yield self.create_text_message(f"Error: Failed to submit video generation request: {response.text}")
                    return
                
                res = response.json()
                request_id = res.get("requestId")
                if not request_id:
                    yield self.create_text_message("Error: Failed to get request ID")
                    return
                
            except requests.exceptions.Timeout as e:
                yield self.create_text_message(f"Error: Request timeout ({REQUEST_TIMEOUT} seconds), please check your network connection or try again later: {str(e)}")
                return
            except requests.exceptions.SSLError as e:
                yield self.create_text_message(f"Error: SSL connection error: {str(e)}")
                return
            except requests.exceptions.ConnectionError as e:
                yield self.create_text_message(f"Error: Connection error: {str(e)}")
                return
            except requests.exceptions.RequestException as e:
                yield self.create_text_message(f"Error: Request exception: {str(e)}")
                return
            except Exception as e:
                stack_trace = traceback.format_exc()
                yield self.create_text_message(f"Error: Failed to send request: {str(e)}\n{stack_trace}")
                return
            
            # Poll status - extend to at least 5 minutes (300 seconds)
            max_retries = 300  # Increase retry count to meet 5-minute requirement
            interval = 2  # Shorten interval for more frequent checks
            total_wait_time = 0  # Track total wait time
            max_wait_time = 300  # Maximum wait time is 5 minutes
            
            # Notify user that video generation has started
            yield self.create_text_message(self._log_message(f"Video generation request submitted (ID: {request_id}). Waiting for results (max wait time: 5 minutes)..."))
            
            attempt = 0
            last_status = None
            while total_wait_time < max_wait_time:
                attempt += 1
                try:
                    # Check video generation status
                    status_payload = {"requestId": request_id}
                    
                    try:
                        status_response = requests.post(
                            SILICONFLOW_VIDEO_STATUS_ENDPOINT,
                            json=status_payload,
                            headers=headers,
                            timeout=REQUEST_TIMEOUT
                        )
                        
                        if status_response.status_code != 200:
                            if attempt % 10 == 0:  # Only show every 10th attempt
                                yield self.create_text_message(self._log_message(f"Error: Failed to get status. Status code: {status_response.status_code}"))
                            time.sleep(interval)
                            total_wait_time += interval
                            continue
                        
                        status_data = status_response.json()
                        status = status_data.get("status")
                        
                        # Only output on status change
                        if status != last_status:
                            yield self.create_text_message(self._log_message(f"Status changed: {last_status or 'Initial'} -> {status}"))
                            last_status = status
                        
                        if status == "Succeed":
                            videos = status_data.get("results", {}).get("videos", [])
                            if videos and len(videos) > 0:
                                video_url = videos[0].get("url")
                                yield self.create_image_message(video_url)
                                yield self.create_text_message(self._log_message("Video generation successful! Click the link above to view. Link valid for 1 hour."))
                                return
                            else:
                                yield self.create_text_message(self._log_message("Error: Status shows success but no video URL found"))
                                return
                        
                        elif status in ["InQueue", "InProgress"]:
                            # Progress update every 60 seconds
                            if total_wait_time > 0 and total_wait_time % 60 == 0:
                                yield self.create_text_message(self._log_message(f"Video still generating, waited approximately {total_wait_time} seconds..."))
                            time.sleep(interval)
                            total_wait_time += interval
                            continue
                        
                        elif status == "Failed":
                            reason = status_data.get("reason", "Contact support at contact@siliconflow.cn for assistance.")
                            yield self.create_text_message(self._log_message(f"Error: Video generation failed. Reason: {reason}"))
                            return
                        
                        else:
                            reason = status_data.get("reason", "Unknown status")
                            if attempt % 10 == 0:  # Limit output frequency
                                yield self.create_text_message(self._log_message(f"Warning: Unknown status '{status}'. Reason: {reason}"))
                            if total_wait_time > 60:  # If we've waited over a minute with unknown status
                                time.sleep(interval)
                                total_wait_time += interval
                                continue
                            
                    except requests.exceptions.Timeout as e:
                        if attempt % 10 == 0:  # Every 10th attempt
                            yield self.create_text_message(self._log_message(f"Warning: Status check timed out ({REQUEST_TIMEOUT}s), retrying..."))
                        time.sleep(interval)
                        total_wait_time += interval
                        continue
                    except requests.exceptions.RequestException as e:
                        if attempt % 10 == 0:  # Every 10th attempt
                            yield self.create_text_message(self._log_message(f"Warning: Request error during status check: {str(e)}"))
                        time.sleep(interval)
                        total_wait_time += interval
                        continue
                    
                except Exception as e:
                    # Only show every 10th attempt to reduce noise
                    if attempt % 10 == 0:
                        yield self.create_text_message(self._log_message(f"Warning: Error checking video status: {str(e)}"))
                    time.sleep(interval)
                    total_wait_time += interval
            
            # Timeout but no result
            yield self.create_text_message(self._log_message(f"Notice: Waited over {max_wait_time} seconds. Video may still be generating. Your request ID: {request_id}"))
            
        except Exception as e:
            yield self.create_text_message(self._log_message(f"Error: Request failed: {str(e)}")) 