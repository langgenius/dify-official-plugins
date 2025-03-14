import json
import os
import traceback
import requests
from typing import Mapping, List, Dict, Any
from werkzeug import Request, Response
from dify_plugin import Endpoint
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dify_plugin.invocations.file import UploadFileResponse


class SlackEndpoint(Endpoint):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        """
        Invokes the endpoint with the given request.
        Always responds to Slack messages for debugging purposes.
        """
        retry_num = r.headers.get("X-Slack-Retry-Num")
        if (not settings.get("allow_retry") and (r.headers.get("X-Slack-Retry-Reason") == "http_timeout" or ((retry_num is not None and int(retry_num) > 0)))):
            return Response(status=200, response="ok")
        data = r.get_json()
        print("[DEBUG] Received data:", data)

        # Handle Slack URL verification challenge
        if data.get("type") == "url_verification":
            return Response(
                response=json.dumps({"challenge": data.get("challenge")}),
                status=200,
                content_type="application/json"
            )
        
        if (data.get("type") == "event_callback"):
            event = data.get("event")
            event_type = event.get("type")
            
            # Get the bot token for API calls
            token = settings.get("bot_token")
            client = WebClient(token=token)
            
            # Get channel ID from the event
            channel_id = event.get("channel", "")
            
            # DEBUG: Always process for debugging
            should_process = True
            message = ""
            blocks = []
            
            if event_type == "app_mention":
                message = event.get("text", "")
                if message.startswith("<@"):
                    message = message.split("> ", 1)[1] if "> " in message else message
                blocks = event.get("blocks", [])
                if blocks and blocks[0].get("elements") and blocks[0].get("elements")[0].get("elements"):
                    blocks[0]["elements"][0]["elements"] = blocks[0].get("elements")[0].get("elements")[1:]
            
            elif event_type == "message":
                # DEBUG: Process all messages, even from bots
                message = event.get("text", "")
                blocks = event.get("blocks", [])
            
            # Add debug prefix to message
            message = f"[DEBUG] {message}" if message else "[DEBUG] Empty message"
            
            if should_process:
                try: 
                    # Process files from Slack if enabled
                    files = event.get("files", [])
                    file_info = ""
                    uploaded_files: List[UploadFileResponse] = []

                    if settings.get("process_slack_files", False) and files:
                        uploaded_files = self._process_slack_files(client, files)
                        if uploaded_files:
                            file_info = "\n\nFiles processed: " + ", ".join([f['filename'] for f in uploaded_files])

                    # Invoke Dify app with the message and any uploaded files
                    inputs = {}
                    if uploaded_files:
                        inputs["files"] = uploaded_files
                    
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
                    dify_files = []
                    if settings.get("process_dify_files", False) and response.get("files"):
                        dify_files = self._upload_files_to_slack(client, response.get("files", []), channel_id)
                    
                    # Send response to Slack
                    result = client.chat_postMessage(
                        channel=channel_id,
                        text=answer,
                        thread_ts=event.get("thread_ts") or event.get("ts")
                    )
                    
                    return Response(
                        status=200,
                        response=json.dumps(result),
                        content_type="application/json"
                    )
                except SlackApiError as slack_error:
                    # Log the error and send debug info
                    error_message = f"[DEBUG] Slack API Error: {slack_error}"
                    print(error_message)
                    
                    try:
                        # Try to send error message to Slack
                        client.chat_postMessage(
                            channel=channel_id,
                            text=error_message,
                            thread_ts=event.get("thread_ts") or event.get("ts")
                        )
                    except:
                        pass
                    
                    return Response(
                        status=200,
                        response=error_message,
                        content_type="text/plain",
                    )
                except Exception as e:
                    err = traceback.format_exc()
                    error_message = f"[DEBUG] Error processing request: {e}\n{err}"
                    print(error_message)
                    
                    try:
                        # Try to send error message to Slack
                        client.chat_postMessage(
                            channel=channel_id,
                            text=error_message,
                            thread_ts=event.get("thread_ts") or event.get("ts")
                        )
                    except:
                        pass
                    
                    return Response(
                        status=200,
                        response=error_message,
                        content_type="text/plain",
                    )
        
        # For any other type of request, return a debug response
        return Response(
            status=200, 
            response="[DEBUG] Received non-event request"
        )
    
    def _process_slack_files(self, client: WebClient, files: List[Dict[str, Any]]) -> List[UploadFileResponse]:
        """
        Process files from Slack:
        1. Download the files using the bot token
        2. Upload them to Dify storage
        3. Return the uploaded file information
        """
        uploaded_files: List[UploadFileResponse] = []
        
        for file in files:
            try:
                # Get file info
                file_name = file.get("name")
                file_type = file.get("mimetype", "application/octet-stream")
                file_url = file.get("url_private_download")
                
                if not file_url or not file_name:
                    continue
                
                # Download the file content
                headers = {"Authorization": f"Bearer {client.token}"}
                file_response = requests.get(file_url, headers=headers)
                
                if file_response.status_code != 200:
                    print(f"Failed to download file {file_name}: {file_response.status_code}")
                    continue
                
                # Upload to Dify storage
                file_content = file_response.content

                storage_file = self.session.file.upload(
                    filename=file_name,
                    content=file_content,
                    mimetype=file_type
                )

                print(f"Uploaded file {file_name} to Dify storage: {storage_file}")
                
                # Add to uploaded files list
                if storage_file:
                    uploaded_files.append(storage_file)
            except Exception as e:
                print(f"Error processing file {file.get('name')}: {e}")
        
        return uploaded_files
    
    def _upload_files_to_slack(self, client: WebClient, files: List[Dict[str, Any]], channel_id: str) -> List[Dict[str, Any]]:
        """
        Upload files from Dify response to Slack:
        1. Download the files from Dify storage
        2. Upload them to Slack
        3. Return the uploaded file information
        """
        uploaded_files = []
        
        for file in files:
            try:
                file_id = file.get("file_id")
                file_name = file.get("filename", "file")
                
                if not file_id:
                    continue
                
                # Download file from Dify storage
                file_content = self.session.storage.download_file(file_id)
                
                if not file_content:
                    print(f"Failed to download file {file_name} from Dify storage")
                    continue
                
                # Create a temporary file
                temp_file_path = f"/tmp/{file_name}"
                with open(temp_file_path, "wb") as f:
                    f.write(file_content)
                
                # Upload to Slack
                result = client.files_upload_v2(
                    channel=channel_id,
                    file=temp_file_path,
                    filename=file_name
                )
                
                # Clean up temporary file
                os.remove(temp_file_path)
                
                # Add to uploaded files list
                if result and result.get("file"):
                    uploaded_files.append({
                        "id": result["file"]["id"],
                        "name": file_name,
                        "url": result["file"].get("permalink", "")
                    })
            except Exception as e:
                print(f"Error uploading file {file.get('filename')} to Slack: {e}")
        
        return uploaded_files
