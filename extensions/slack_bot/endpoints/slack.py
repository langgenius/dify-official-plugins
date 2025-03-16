import json
import os
import traceback
import requests
from typing import Mapping, List, Dict, Any, Optional
from werkzeug import Request, Response
from dify_plugin import Endpoint
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dify_plugin.invocations.file import UploadFileResponse


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
            print(f"data: {data}")
            event = data.get("event")
            event_type = event.get("type")
            user = event.get("user")
            if (user == ""):
                return Response(status=200, response="ok")
            
            print(f"event_type: {event_type}")

            # Get configured event types and channel
            configured_event_types = settings.get("event_types", "app_mention")
            configured_channel_name = settings.get("channel_name", "")
            
            # Get the bot token for API calls
            token = settings.get("bot_token")
            client = WebClient(token=token)
            
            # Check if the event is from the configured channel (if specified)
            channel_id = event.get("channel", "")
            print(f"channel_id: {channel_id}")
            print(f"configured_channel_name: {configured_channel_name}")
            # If a channel name is configured, check if this event is from that channel
            if configured_channel_name:
                try:
                    # Get channel info to check if it matches the configured name
                    channel_info = client.conversations_info(channel=channel_id)
                    print(f"channel_info: {channel_info}")
                    if channel_info["channel"]["name"] != configured_channel_name:
                        print(f"Not the configured channel: {channel_info["channel"]["name"]}")
                        return Response(status=200, response="ok")  # Not the configured channel
                except SlackApiError as e:
                    print(f"Error getting channel info: {e}")
                    # If we can't get channel info, continue processing
                    pass
            
            # Process based on event type
            should_process = False
            message = ""
            blocks = []
            print(f"should_process: {should_process}")
            
            if event_type == "app_mention" and (configured_event_types == "app_mention" or configured_event_types == "both"):
                should_process = True
                message = event.get("text", "")
                print(f"message: {message}")
                if message.startswith("<@"):
                    message = message.split("> ", 1)[1] if "> " in message else message
                    blocks = event.get("blocks", [])
                    # If exist files, add file names
                    if len(event.get("files", [])) > 0:
                        message += "\n\nFiles attached: " + ", ".join([f['name'] for f in event.get("files", [])])

                    if blocks and blocks[0].get("elements") and blocks[0].get("elements")[0].get("elements"):
                        blocks[0]["elements"][0]["elements"] = blocks[0].get("elements")[0].get("elements")[1:]
            
            elif event_type == "message" and (configured_event_types == "message" or configured_event_types == "both"):
                # Only process messages not from bots and not from app mentions (those are handled separately)
                if not event.get("bot_id") and not event.get("subtype") == "bot_message" and not event.get("text", "").startswith("<@"):
                    should_process = True
                    message = event.get("text", "")
                    # If exist files, add file names
                    if len(event.get("files", [])) > 0:
                        message += "\n\nFiles attached: " + ", ".join([f['name'] for f in event.get("files", [])])
                    blocks = event.get("blocks", [])
            
            if should_process and len(message) > 0:
                try:
                    # Process files from Slack if enabled
                    files = event.get("files", [])
                    file_info = ""
                    uploaded_files: List[Dict[str, Any]] = []

                    if settings.get("process_slack_files", False) and files:
                        print("_process_slack_files: start")    
                        uploader = FileUploader()
                        uploaded_files = uploader.process_slack_files(client=client, files=files)
                        print("_process_slack_files: end")
                        print(f"uploaded_files: {uploaded_files}")

                        if uploaded_files:
                            file_info = "\n\nFiles processed: " + ", ".join([f['name'] for f in uploaded_files])

                    # Invoke Dify app with the message and any uploaded files
                    inputs = {}
                    if uploaded_files:
                        inputs = {
                            "files": [
                                {
                                    "upload_file_id": f["id"],
                                    "type": f["type"],
                                    "transfer_method": "local_file"
                                }
                                for f in uploaded_files
                            ]
                        }

                    print(f"inputs: {inputs}")
                    
                    # Invoke Dify app workflow
                    response = self.session.app.chat.invoke(
                        app_id=settings["app"]["app_id"],
                        query=message,
                        inputs=inputs,
                        response_mode="blocking",
                    )
                    
                    # Process the response
                    answer = response.get("answer", "")
                    if file_info:
                        answer += file_info
                    
                    # Check if Dify response contains files and process_dify_files is enabled
                    # dify_files = []
                    # if settings.get("process_dify_files", False) and response.get("files"):
                    #     dify_files = self._upload_files_to_slack(client, response.get("files", []), channel_id)
                    
                    # For regular messages without blocks, create a simple response
                    if event_type == "message" and (not event.get("blocks") or len(event.get("blocks", [])) == 0):
                        result = client.chat_postMessage(
                            channel=channel_id,
                            text=answer,
                            thread_ts=event.get("thread_ts") or event.get("ts")  # Reply in thread if it's a thread
                        )
                    # For app mentions with blocks
                    else:
                        if blocks and blocks[0].get("elements") and blocks[0].get("elements")[0].get("elements"):
                            blocks[0]["elements"][0]["elements"][0]["text"] = answer
                        result = client.chat_postMessage(
                            channel=channel_id,
                            text=answer,
                            blocks=blocks,
                            thread_ts=event.get("thread_ts") or event.get("ts")  # Reply in thread if it's a thread
                        )
                    
                    # Convert SlackResponse to a serializable dictionary
                    result_dict = {
                        "ok": result.get("ok", False),
                        "channel": result.get("channel", ""),
                        "ts": result.get("ts", ""),
                        "message": result.get("message", {})
                    }
                    
                    return Response(
                        status=200,
                        response=json.dumps(result_dict),
                        content_type="application/json"
                    )
                except SlackApiError as slack_error:
                    # Log the error and re-raise
                    print(f"Slack API Error: {slack_error}")
                    raise slack_error
                except Exception as e:
                    err = traceback.format_exc()
                    client.chat_postMessage(
                        channel=channel_id,
                        text="Sorry, I'm having trouble processing your request. Please try again later." + str(err),
                        thread_ts=event.get("thread_ts") or event.get("ts")  # Reply in thread if it's a thread
                    )
                    print(f"Error processing request: {e}")
                    return Response(
                        status=200,
                        response="Sorry, I'm having trouble processing your request. Please try again later." + str(err),
                        content_type="text/plain",
                    )
            else:
                return Response(status=200, response="ok")
        else:
            return Response(status=200, response="ok")
   

class FileUploader:
    """
    A utility class to handle file uploads to Dify API
    """
    
    def __init__(self, session=None, dify_base_url="http://api:5001/v1", dify_api_key=""):
        """
        Initialize the FileUploader
        
        Args:
            session: The Dify plugin session object (if available)
            dify_base_url: The base URL for Dify API (if session not available)
            dify_api_key: The API key for Dify API (if session not available)
        """
        self.session = session
        self.dify_base_url = dify_base_url
        self.dify_api_key = dify_api_key
        
    def upload_file_via_session(self, filename: str, content: bytes, mimetype: str) -> Optional[Dict[str, Any]]:
        """
        Upload a file using the Dify plugin session
        
        Args:
            filename: The name of the file
            content: The content of the file as bytes
            mimetype: The MIME type of the file
            
        Returns:
            Dictionary with file information or None if upload fails
        """
        try:
            print(f"Uploading file via session: {filename}, mimetype: {mimetype}, content size: {len(content)} bytes")
            
            # Use a simple test file first to verify the API is working
            test_result = self.session.file.upload(
                filename="test.txt", 
                content=b"test content", 
                mimetype="text/plain"
            )
            print(f"Test upload result: {test_result}")
            
            # Now try the actual file
            storage_file = self.session.file.upload(
                filename=filename,
                content=content,
                mimetype=mimetype
            )
            
            print(f"Uploaded file to Dify storage: {storage_file}")
            
            if storage_file:
                # Convert to app parameter format
                return storage_file.to_app_parameter()
            return None
        except Exception as e:
            print(f"Error uploading file via session: {e}")
            traceback.print_exc()
            return None
    
    def upload_file_via_api(self, filename: str, content: bytes, mimetype: str) -> Optional[Dict[str, Any]]:
        """
        Upload a file using direct API calls to Dify
        
        Args:
            filename: The name of the file
            content: The content of the file as bytes
            mimetype: The MIME type of the file
            
        Returns:
            Dictionary with file information or None if upload fails
        """
        if not self.dify_base_url or not self.dify_api_key:
            print("Error: dify_base_url and dify_api_key must be provided for direct API upload")
            return None
        
        try:
            print(f"Uploading file via API: {filename}, mimetype: {mimetype}, content size: {len(content)} bytes")
            
            # Prepare the file upload endpoint
            upload_url = f"{self.dify_base_url}/files/upload"
            headers = {
                "Authorization": f"Bearer {self.dify_api_key}"
            }
            
            # Create a temporary file to upload
            temp_file_path = f"/tmp/{filename}"
            with open(temp_file_path, "wb") as f:
                f.write(content)
            
            # Upload the file
            files = {
                'file': (filename, open(temp_file_path, 'rb'), mimetype)
            }
            
            response = requests.post(upload_url, headers=headers, files=files)
            
            # Clean up the temporary file
            os.remove(temp_file_path)
            
            if response.status_code == 201 or response.status_code == 200:
                result = response.json()
                print(f"File upload API response: {result}")
                
                # Format the response to match Dify plugin format
                if 'id' in result:
                    return {
                        'id': result['id'],
                        'name': result.get('name', filename),
                        'size': result.get('size', len(content)),
                        'extension': result.get('extension', ''),
                        'mime_type': result.get('mime_type', mimetype),
                        'type': UploadFileResponse.Type.from_mime_type(mimetype).value,
                        'url': result.get('url', '')
                    }
            else:
                print(f"File upload API error: {response.status_code}, {response.text}")
            
            return None
        except Exception as e:
            print(f"Error uploading file via API: {e}")
            traceback.print_exc()
            return None
    
    def process_slack_files(self, client, files: List[Dict[str, Any]], dify_base_url=None, dify_api_key=None) -> List[Dict[str, Any]]:
        """
        Process files from Slack:
        1. Download the files using the bot token
        2. Upload them to Dify storage
        3. Return the uploaded file information
        
        Args:
            client: The Slack WebClient
            files: List of file information from Slack
            dify_base_url: Optional Dify base URL for direct API upload
            dify_api_key: Optional Dify API key for direct API upload
            
        Returns:
            List of uploaded file information
        """
        uploaded_files = []
        
        # Set API parameters if provided
        if dify_base_url:
            self.dify_base_url = dify_base_url
        if dify_api_key:
            self.dify_api_key = dify_api_key
        
        for file in files:
            try:
                # Get file info
                file_name = file.get("name")
                file_type = file.get("mimetype", "application/octet-stream")
                file_url = file.get("url_private_download")
                
                if not file_url or not file_name:
                    print(f"Missing file URL or name: {file}")
                    continue
                
                # Download the file content
                headers = {"Authorization": f"Bearer {client.token}"}
                file_response = requests.get(file_url, headers=headers)
                
                if file_response.status_code != 200:
                    print(f"Failed to download file {file_name}: {file_response.status_code}")
                    continue
                
                print(f"Downloaded file from Slack: {file_name}, {file_type}, size: {len(file_response.content)} bytes")
                
                # Try uploading via session first
                if self.session:
                    storage_file = self.upload_file_via_session(file_name, file_response.content, file_type)
                    if storage_file:
                        uploaded_files.append(storage_file)
                        continue
                
                # If session upload fails or session not available, try direct API upload
                if self.dify_base_url and self.dify_api_key:
                    storage_file = self.upload_file_via_api(file_name, file_response.content, file_type)
                    if storage_file:
                        uploaded_files.append(storage_file)

            except Exception as e:
                print(f"Error processing file {file.get('name')}: {e}")
                traceback.print_exc()
        
        return uploaded_files
