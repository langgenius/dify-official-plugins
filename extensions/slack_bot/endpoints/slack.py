import json
import os
import logging
import traceback
import requests
from typing import Mapping, List, Dict, Any, Optional, Tuple
from werkzeug import Request, Response
from dify_plugin import Endpoint
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dify_plugin.invocations.file import UploadFileResponse


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SlackEndpoint(Endpoint):
    """
    Endpoint for handling Slack events and integrating with Dify.
    """
    
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        """
        Invokes the endpoint with the given request.
        
        Args:
            r: The incoming request
            values: Request values
            settings: Configuration settings
            
        Returns:
            Response object
        """
        # Handle retry logic
        if self._should_ignore_retry(r, settings):
            return Response(status=200, response="ok")
            
        data = r.get_json()
        
        # Handle URL verification challenge
        if data.get("type") == "url_verification":
            return self._handle_url_verification(data)
            
        # Handle event callbacks
        if data.get("type") == "event_callback":
            return self._handle_event_callback(data, settings)
            
        # Default response for unhandled event types
        return Response(status=200, response="ok")
    
    def _should_ignore_retry(self, r: Request, settings: Mapping) -> bool:
        """
        Determines if a retry request should be ignored.
        
        Args:
            r: The incoming request
            settings: Configuration settings
            
        Returns:
            True if the request should be ignored, False otherwise
        """
        retry_num = r.headers.get("X-Slack-Retry-Num")
        retry_reason = r.headers.get("X-Slack-Retry-Reason")
        
        return (not settings.get("allow_retry") and 
                (retry_reason == "http_timeout" or 
                 (retry_num is not None and int(retry_num) > 0)))
    
    def _handle_url_verification(self, data: Dict[str, Any]) -> Response:
        """
        Handles Slack URL verification challenge.
        
        Args:
            data: The request data
            
        Returns:
            Response with the challenge
        """
        return Response(
            response=json.dumps({"challenge": data.get("challenge")}),
            status=200,
            content_type="application/json"
        )
    
    def _handle_event_callback(self, data: Dict[str, Any], settings: Mapping) -> Response:
        """
        Handles Slack event callbacks.
        
        Args:
            data: The request data
            settings: Configuration settings
            
        Returns:
            Response object
        """
        logger.info("Handling event callback")
        event = data.get("event", {})
        event_type = event.get("type", "")
        user = event.get("user", "")
        
        # Ignore empty user events
        if not user:
            return Response(status=200, response="ok")
        
        # Check if user is in ignore list
        ignore_user_ids = settings.get("ignore_user_ids", "").split(",")
        ignore_user_ids = [user_id.strip() for user_id in ignore_user_ids if user_id.strip()]
        if user in ignore_user_ids:
            logger.info(f"Ignoring message from user in ignore list: {user}")
            return Response(status=200, response="ok")
            
        logger.info(f"Event type: {event_type}")
        
        # Initialize Slack client
        token = settings.get("bot_token")
        client = WebClient(token=token)
        
        # Get channel information
        channel_id = event.get("channel", "")
        if not self._is_valid_channel(client, channel_id, settings):
            return Response(status=200, response="ok")
        
        # Process the event based on type
        message_data = self._extract_message_data(event, event_type, settings)
        
        if not message_data["should_process"] or not message_data["message"]:
            return Response(status=200, response="ok")
            
        # Process the message and respond
        try:
            return self._process_and_respond(
                client, 
                event, 
                message_data, 
                settings, 
                channel_id, 
                event_type
            )
        except SlackApiError as slack_error:
            logger.error(f"Slack API Error: {slack_error}")
            raise slack_error
        except Exception as e:
            return self._handle_processing_error(client, event, channel_id, e)
    
    def _is_valid_channel(self, client: WebClient, channel_id: str, settings: Mapping) -> bool:
        """
        Checks if the event is from a valid channel.
        
        Args:
            client: Slack WebClient
            channel_id: Channel ID
            settings: Configuration settings
            
        Returns:
            True if the channel is valid, False otherwise
        """
        configured_channel_name = settings.get("channel_name", "")
        
        if not configured_channel_name:
            return True
            
        try:
            channel_info = client.conversations_info(channel=channel_id)
            channel_name = channel_info["channel"]["name"]
            
            if channel_name != configured_channel_name:
                logger.info(f"Not the configured channel: {channel_name}")
                return False
                
            return True
        except SlackApiError as e:
            logger.warning(f"Error getting channel info: {e}")
            # Continue processing if we can't get channel info
            return True
    
    def _extract_message_data(self, event: Dict[str, Any], event_type: str, settings: Mapping) -> Dict[str, Any]:
        """
        Extracts message data from the event.
        
        Args:
            event: The event data
            event_type: The event type
            settings: Configuration settings
            
        Returns:
            Dictionary with message data
        """
        configured_event_types = settings.get("event_types", "app_mention")
        should_process = False
        message = ""
        blocks = []
        
        if event_type == "app_mention" and (configured_event_types == "app_mention" or configured_event_types == "both"):
            should_process, message, blocks = self._extract_app_mention_data(event)
        elif event_type == "message" and (configured_event_types == "message" or configured_event_types == "both"):
            should_process, message, blocks = self._extract_message_event_data(event)
            
        return {
            "should_process": should_process,
            "message": message,
            "blocks": blocks
        }
    
    def _extract_app_mention_data(self, event: Dict[str, Any]) -> Tuple[bool, str, List]:
        """
        Extracts data from app_mention events.
        
        Args:
            event: The event data
            
        Returns:
            Tuple of (should_process, message, blocks)
        """
        message = event.get("text", "")
        blocks = event.get("blocks", [])
        
        if message.startswith("<@"):
            # Remove the bot mention from the message
            message = message.split("> ", 1)[1] if "> " in message else message
            
            # Add file names if files are attached
            files = event.get("files", [])
            if files:
                message += "\n\nFiles attached: " + ", ".join([f['name'] for f in files])
                
            # Remove the mention from blocks if present
            if blocks and blocks[0].get("elements") and blocks[0].get("elements")[0].get("elements"):
                blocks[0]["elements"][0]["elements"] = blocks[0].get("elements")[0].get("elements")[1:]
                
        return True, message, blocks
    
    def _extract_message_event_data(self, event: Dict[str, Any]) -> Tuple[bool, str, List]:
        """
        Extracts data from message events.
        
        Args:
            event: The event data
            
        Returns:
            Tuple of (should_process, message, blocks)
        """
        # Only process messages not from bots and not from app mentions
        if event.get("bot_id") or event.get("subtype") == "bot_message" or event.get("text", "").startswith("<@"):
            return False, "", []
            
        message = event.get("text", "")
        blocks = event.get("blocks", [])
        
        # Add file names if files are attached
        files = event.get("files", [])
        if files:
            message += "\n\nFiles attached: " + ", ".join([f['name'] for f in files])
            
        return True, message, blocks
    
    def _process_and_respond(
        self, 
        client: WebClient, 
        event: Dict[str, Any], 
        message_data: Dict[str, Any], 
        settings: Mapping, 
        channel_id: str, 
        event_type: str
    ) -> Response:
        """
        Processes the message and responds to Slack.
        
        Args:
            client: Slack WebClient
            event: The event data
            message_data: Extracted message data
            settings: Configuration settings
            channel_id: Channel ID
            event_type: Event type
            
        Returns:
            Response object
        """
        message = message_data["message"]
        blocks = message_data["blocks"]
        
        # Process files from Slack if enabled
        uploaded_files, file_info = self._process_files(client, event, settings)
        
        # Prepare inputs for Dify
        inputs = self._prepare_dify_inputs(uploaded_files)
        
        # Invoke Dify app
        response = self._invoke_dify_app(message, inputs, settings)
        
        # Process the response
        answer = response.get("answer", "")
        if file_info:
            answer += file_info
            
        # Send response to Slack
        result = self._send_slack_response(client, channel_id, event, event_type, answer, blocks)
        
        # Return response
        return Response(
            status=200,
            response=json.dumps(self._format_slack_result(result)),
            content_type="application/json"
        )
    
    def _process_files(
        self, 
        client: WebClient, 
        event: Dict[str, Any], 
        settings: Mapping
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Processes files from Slack.
        
        Args:
            client: Slack WebClient
            event: The event data
            settings: Configuration settings
            
        Returns:
            Tuple of (uploaded_files, file_info)
        """
        files = event.get("files", [])
        uploaded_files = []
        file_info = ""
        
        if settings.get("process_slack_files", False) and files:
            logger.info("Processing Slack files")
            # Pass Dify API token if configured
            dify_api_token = settings.get("dify_api_token", "")
            uploader = FileUploader(
                session=self.session,
                dify_api_key=dify_api_token if dify_api_token else None
            )
            uploaded_files = uploader.process_slack_files(client=client, files=files)
            
            if uploaded_files:
                file_info = "\n\nFiles processed: " + ", ".join([f['name'] for f in uploaded_files])
                
        return uploaded_files, file_info
    
    def _prepare_dify_inputs(self, uploaded_files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Prepares inputs for Dify app.
        
        Args:
            uploaded_files: List of uploaded files
            
        Returns:
            Dictionary with inputs for Dify
        """
        if not uploaded_files:
            return {}
            
        return {
            "files": [
                {
                    "upload_file_id": f["id"],
                    "type": f["type"],
                    "transfer_method": "local_file"
                }
                for f in uploaded_files
            ]
        }
    
    def _invoke_dify_app(
        self, 
        message: str, 
        inputs: Dict[str, Any], 
        settings: Mapping
    ) -> Dict[str, Any]:
        """
        Invokes the Dify app.
        
        Args:
            message: The message to send
            inputs: Additional inputs
            settings: Configuration settings
            
        Returns:
            Response from Dify
        """
        logger.info(f"Invoking Dify app with message: {message}")
        return self.session.app.chat.invoke(
            app_id=settings["app"]["app_id"],
            query=message,
            inputs=inputs,
            response_mode="blocking",
        )
    
    def _send_slack_response(
        self, 
        client: WebClient, 
        channel_id: str, 
        event: Dict[str, Any], 
        event_type: str, 
        answer: str, 
        blocks: List
    ) -> Dict[str, Any]:
        """
        Sends response to Slack.
        
        Args:
            client: Slack WebClient
            channel_id: Channel ID
            event: The event data
            event_type: Event type
            answer: The answer to send
            blocks: Message blocks
            
        Returns:
            Result from Slack API
        """
        thread_ts = event.get("thread_ts") or event.get("ts")
        
        # For regular messages without blocks
        if event_type == "message" and (not event.get("blocks") or len(event.get("blocks", [])) == 0):
            return client.chat_postMessage(
                channel=channel_id,
                text=answer,
                thread_ts=thread_ts
            )
        # For app mentions with blocks
        else:
            if blocks and blocks[0].get("elements") and blocks[0].get("elements")[0].get("elements"):
                blocks[0]["elements"][0]["elements"][0]["text"] = answer
                
            return client.chat_postMessage(
                channel=channel_id,
                text=answer,
                blocks=blocks,
                thread_ts=thread_ts
            )
    
    def _format_slack_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Formats Slack API result for response.
        
        Args:
            result: Result from Slack API
            
        Returns:
            Formatted result
        """
        return {
            "ok": result.get("ok", False),
            "channel": result.get("channel", ""),
            "ts": result.get("ts", ""),
            "message": result.get("message", {})
        }
    
    def _handle_processing_error(
        self, 
        client: WebClient, 
        event: Dict[str, Any], 
        channel_id: str, 
        error: Exception
    ) -> Response:
        """
        Handles errors during processing.
        
        Args:
            client: Slack WebClient
            event: The event data
            channel_id: Channel ID
            error: The exception
            
        Returns:
            Response object
        """
        err_trace = traceback.format_exc()
        error_message = f"Sorry, I'm having trouble processing your request. Please try again later."
        
        logger.error(f"Error processing request: {error}")
        logger.error(err_trace)
        
        # Send error message to Slack
        thread_ts = event.get("thread_ts") or event.get("ts")
        try:
            client.chat_postMessage(
                channel=channel_id,
                text=error_message,
                thread_ts=thread_ts
            )
        except Exception as e:
            logger.error(f"Error sending error message to Slack: {e}")
        
        return Response(
            status=200,
            response=error_message,
            content_type="text/plain",
        )


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
        self.logger = logging.getLogger(__name__ + ".FileUploader")
        
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
            self.logger.info(f"Uploading file via session: {filename}, mimetype: {mimetype}, size: {len(content)} bytes")
            
            # Upload the file
            storage_file = self.session.file.upload(
                filename=filename,
                content=content,
                mimetype=mimetype
            )
            
            self.logger.info(f"Uploaded file to Dify storage: {storage_file}")
            
            if storage_file:
                # Convert to app parameter format
                return storage_file.to_app_parameter()
            return None
        except Exception as e:
            self.logger.error(f"Error uploading file via session: {e}")
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
            self.logger.error("Error: dify_base_url and dify_api_key must be provided for direct API upload")
            return None
        
        try:
            self.logger.info(f"Uploading file via API: {filename}, mimetype: {mimetype}, size: {len(content)} bytes")
            
            # Prepare the file upload endpoint
            upload_url = f"{self.dify_base_url}/files/upload"
            headers = {
                "Authorization": f"Bearer {self.dify_api_key}"
            }
            
            # Use a context manager for the temporary file
            temp_file_path = f"/tmp/{filename}"
            try:
                with open(temp_file_path, "wb") as f:
                    f.write(content)
                
                # Upload the file
                with open(temp_file_path, 'rb') as f:
                    files = {'file': (filename, f, mimetype)}
                    response = requests.post(upload_url, headers=headers, files=files)
            finally:
                # Clean up the temporary file
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
            
            if response.status_code in (200, 201):
                result = response.json()
                self.logger.info(f"File upload API response: {result}")
                
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
                self.logger.error(f"File upload API error: {response.status_code}, {response.text}")
            
            return None
        except Exception as e:
            self.logger.error(f"Error uploading file via API: {e}")
            traceback.print_exc()
            return None
    
    def process_slack_files(self, client: WebClient, files: List[Dict[str, Any]], 
                           dify_base_url: Optional[str] = None, 
                           dify_api_key: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    self.logger.warning(f"Missing file URL or name: {file}")
                    continue
                
                # Download the file content
                headers = {"Authorization": f"Bearer {client.token}"}
                file_response = requests.get(file_url, headers=headers)
                
                if file_response.status_code != 200:
                    self.logger.error(f"Failed to download file {file_name}: {file_response.status_code}")
                    continue
                
                self.logger.info(f"Downloaded file from Slack: {file_name}, {file_type}, size: {len(file_response.content)} bytes")
                
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
                self.logger.error(f"Error processing file {file.get('name')}: {e}")
                traceback.print_exc()
        
        return uploaded_files
