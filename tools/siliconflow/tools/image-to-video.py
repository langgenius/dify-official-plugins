from typing import Any, Generator, Optional, Dict, List, Union, BinaryIO
import requests
import base64
import time
import os
import tempfile
import traceback
import json
import httpx
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

SILICONFLOW_VIDEO_CREATE_ENDPOINT = "https://api.siliconflow.cn/v1/video/submit"
SILICONFLOW_VIDEO_STATUS_ENDPOINT = "https://api.siliconflow.cn/v1/video/status"

# Request timeout settings (seconds)
REQUEST_TIMEOUT = 60  # API request timeout
FILE_DOWNLOAD_TIMEOUT = 120  # File download timeout, longer
MAX_DOWNLOAD_RETRIES = 3  # Maximum download retry attempts

# Image-to-video model list
I2V_MODELS = [
    "Wan-AI/Wan2.1-I2V-14B-720P",
    "Wan-AI/Wan2.1-I2V-14B-720P-Turbo"
]


class ImageToVideoTool(Tool):
    def _log_message(self, message):
        """Log message with timestamp"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        return f"[{timestamp}] {message}"
    
    def _download_file(self, url, max_retries=MAX_DOWNLOAD_RETRIES):
        """安全下载文件，带重试机制"""
        debug_info = f"Starting file download: URL={url[:30]}..."
        
        for attempt in range(max_retries):
            try:
                # 使用httpx.Client显式设置超时
                with httpx.Client(timeout=FILE_DOWNLOAD_TIMEOUT) as client:
                    debug_info += f"\nAttempting to download (attempt {attempt+1}/{max_retries})"
                    response = client.get(url)
                    response.raise_for_status()  # 确保请求成功
                    file_size = len(response.content) / 1024  # KB
                    debug_info += f"\nFile download successful: size={file_size:.2f}KB"
                    return response.content, debug_info
            except httpx.TimeoutException as e:
                debug_info += f"\nDownload timeout (attempt {attempt+1}/{max_retries}): {str(e)}"
                if attempt == max_retries - 1:  # 最后一次尝试
                    raise Exception(f"File download timeout ({FILE_DOWNLOAD_TIMEOUT} seconds), attempted {max_retries} times")
                time.sleep(2)  # 重试前等待
            except httpx.ConnectTimeout as e:
                debug_info += f"\nConnection timeout (attempt {attempt+1}/{max_retries}): {str(e)}"
                if attempt == max_retries - 1:
                    raise Exception(f"Connection timeout ({FILE_DOWNLOAD_TIMEOUT} seconds), attempted {max_retries} times: {str(e)}")
                time.sleep(3)  # 连接问题多等一会
            except httpx.HTTPStatusError as e:
                debug_info += f"\nHTTP error (attempt {attempt+1}/{max_retries}): {e.response.status_code} - {str(e)}"
                if attempt == max_retries - 1:
                    raise Exception(f"File download failed: HTTP {e.response.status_code}")
                time.sleep(2)
            except Exception as e:
                debug_info += f"\nDownload exception (attempt {attempt+1}/{max_retries}): {str(e)}"
                if attempt == max_retries - 1:
                    raise
                time.sleep(2)
        
        # 所有重试都失败
        raise Exception(f"File download failed, attempted {max_retries} times")
    
    def _encode_image(self, file_data):
        """Encode image file to base64"""
        try:
            # 记录图片大小
            image_size = len(file_data) / 1024  # KB
            encoded = base64.b64encode(file_data).decode("utf-8")
            encoded_size = len(encoded) / 1024  # KB
            debug_info = f"Image encoding completed: original size={image_size:.2f}KB, encoded size={encoded_size:.2f}KB"
            return f"data:image/png;base64,{encoded}", debug_info
        except Exception as e:
            stack_trace = traceback.format_exc()
            raise Exception(f"Image encoding failed: {str(e)}\nStack trace: {stack_trace}")

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Main invocation logic"""
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.runtime.credentials['siliconFlow_api_key']}",
        }
        
        # 获取模型和基本参数
        model = tool_parameters.get("model")
        prompt = tool_parameters.get("prompt")
        
        # 基本参数检查
        if not model:
            yield self.create_text_message("Error: Please select a video generation model")
            return
        
        if not prompt:
            yield self.create_text_message("Error: Please enter a prompt")
            return
        
        # 输出初始日志
        yield self.create_text_message(self._log_message(f"Starting image-to-video generation with model: {model}"))
        
        # 获取seed参数
        seed = tool_parameters.get("seed")
        
        # 准备基本payload
        payload = {
            "model": model,
            "prompt": prompt,
        }
        
        # 添加seed如果有提供
        if seed is not None:
            payload["seed"] = seed
            
        # 图生视频需要图片和图片尺寸
        image_size = tool_parameters.get("image_size", "1280x720")
        negative_prompt = tool_parameters.get("negative_prompt")
        
        # 设置图片尺寸
        payload["image_size"] = image_size
        
        # 添加负面提示词如果有提供
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
            
        # 处理图片 - 图生视频必须提供图片
        files = tool_parameters.get("image")
        
        # 检查是否提供了图片文件
        if not files:
            yield self.create_text_message("Error: An image is required for image-to-video models. Please upload an image.")
            return
        
        # 处理files类型的变量
        if not isinstance(files, list):
            files = [files]
        
        if len(files) == 0:
            yield self.create_text_message("Error: An image is required for image-to-video models. Please upload an image.")
            return
        
        if len(files) > 1:
            yield self.create_text_message("Note: Multiple images uploaded, only the first image will be used for video generation")
        
        # 获取第一个图片并处理
        file = files[0]
        yield self.create_text_message(self._log_message(f"Processing uploaded image..."))
        
        try:
            # 改进的文件处理逻辑
            file_content = None
            download_debug_info = None
            
            # 检查文件类型并获取文件内容
            if hasattr(file, 'url') and file.url:
                # 如果文件是通过URL提供的，使用专门的下载函数
                file_url = file.url
                yield self.create_text_message(self._log_message(f"Retrieving image from URL: {file_url[:30]}..."))
                try:
                    file_content, download_debug_info = self._download_file(file_url)
                    yield self.create_text_message(self._log_message(download_debug_info))
                except Exception as e:
                    # 下载失败，尝试其他方法
                    yield self.create_text_message(self._log_message(f"Failed to download from URL: {str(e)}, attempting alternative method..."))
            
            # 如果URL下载失败或没有URL，尝试其他方法
            if file_content is None and hasattr(file, 'blob'):
                try:
                    file_content = file.blob
                    yield self.create_text_message(self._log_message(f"Retrieved file data from blob attribute: size={len(file.blob)/1024:.2f}KB"))
                except httpx.ConnectTimeout as e:
                    yield self.create_text_message(self._log_message(f"Failed to retrieve blob attribute: {str(e)}"))
                except Exception as e:
                    yield self.create_text_message(self._log_message(f"Failed to retrieve blob attribute: {str(e)}"))
            
            # 尝试从read方法获取
            if file_content is None and hasattr(file, 'read'):
                try:
                    file_content = file.read()
                    yield self.create_text_message(self._log_message("Retrieved file data from readable object"))
                    # 如果是文件对象，可能需要重置文件指针
                    if hasattr(file, 'seek'):
                        file.seek(0)
                except Exception as e:
                    yield self.create_text_message(self._log_message(f"Failed to retrieve file data from read method: {str(e)}"))
            
            # 尝试作为文件路径处理
            if file_content is None and isinstance(file, str):
                try:
                    with open(file, 'rb') as f:
                        file_content = f.read()
                    yield self.create_text_message(self._log_message(f"Retrieved file data from file path: {file}, size={len(file_content)/1024:.2f}KB"))
                except (TypeError, IOError) as e:
                    yield self.create_text_message(self._log_message(f"Failed to retrieve file data from file path: {str(e)}"))
            
            # 尝试本地文件缓存方式
            if file_content is None and hasattr(file, 'path'):
                try:
                    with open(file.path, 'rb') as f:
                        file_content = f.read()
                    yield self.create_text_message(self._log_message(f"Retrieved file data from local cache path: {file.path}, size={len(file_content)/1024:.2f}KB"))
                except (TypeError, IOError) as e:
                    yield self.create_text_message(self._log_message(f"Failed to retrieve file data from local cache path: {str(e)}"))
            
            # 如果所有方法都失败
            if file_content is None:
                yield self.create_text_message("Error: Unable to retrieve image data. Please try uploading the image again or use a smaller image file")
                return
            
            # 编码图片数据
            try:
                encoded_image, encoding_debug = self._encode_image(file_content)
                payload["image"] = encoded_image
                yield self.create_text_message(self._log_message(encoding_debug))
            except Exception as e:
                yield self.create_text_message(f"Error: Image encoding failed: {str(e)}")
                return
            
        except AttributeError as e:
            stack_trace = traceback.format_exc()
            yield self.create_text_message(f"Error: File variable format error: {str(e)}\n{stack_trace}")
            return
        except Exception as e:
            stack_trace = traceback.format_exc()
            yield self.create_text_message(f"Error: Failed to process image file: {str(e)}\nStack trace:\n{stack_trace}")
            return
        
        try:
            # 发送生成请求
            yield self.create_text_message(self._log_message("Sending video generation request..."))
            
            # 使用我们自己定义的_send_generation_request方法
            # 准备发送请求
            try:
                response = requests.post(
                    SILICONFLOW_VIDEO_CREATE_ENDPOINT, 
                    json=payload, 
                    headers=headers,
                    timeout=REQUEST_TIMEOUT
                )
                
                debug_info = f"Received response: status code={response.status_code}, response size={len(response.text)} bytes"
                yield self.create_text_message(self._log_message(debug_info))
                
                if response.status_code != 200:
                    yield self.create_text_message(f"Error: Failed to submit video generation request: {response.text}")
                    return
                
                res = response.json()
                request_id = res.get("requestId")
                if not request_id:
                    yield self.create_text_message("Error: Request ID not retrieved")
                    return
                
            except requests.exceptions.Timeout as e:
                yield self.create_text_message(f"Error: Request timed out ({REQUEST_TIMEOUT} seconds), please check network connection or try again later: {str(e)}")
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

def image_to_video(
    prompt: str,
    image: Union[str, BinaryIO],
    model: str = "tencent/hunyuan-video",
    image_size: str = "1280x720",
    seed: Optional[int] = None,
    negative_prompt: Optional[str] = None,
) -> dict:
    """
    Generate a video from an image and text prompt using SiliconFlow API.
    
    Args:
        prompt: Text description of the video to generate
        image: Image file to be used as the starting point for video generation
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
    
    # Prepare the image data
    image_data = None
    try:
        if isinstance(image, str):
            # If image is a file path or base64 string
            if os.path.isfile(image):
                with open(image, "rb") as img_file:
                    image_data = base64.b64encode(img_file.read()).decode("utf-8")
            else:
                # Assume it's already a base64 string
                image_data = image
        else:
            # If image is a file-like object
            image_data = base64.b64encode(image.read()).decode("utf-8")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to process image: {str(e)}"
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
        "image": f"data:image/jpeg;base64,{image_data}"
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