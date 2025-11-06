import json
import time
import logging
from collections.abc import Generator
from typing import Any, Optional, Dict

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from bedrock_agentcore.tools.browser_client import BrowserClient

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from provider.utils import ParameterStoreManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentcoreBrowserSessionManagerTool(Tool):

    def _init_browser_session(self, aws_region, session_timeout_seconds) -> dict:
        """Initialize AWS AgentCore Browser session"""
        browser_client = BrowserClient(aws_region)
        browser_client.start(identifier="aws.browser.v1", session_timeout_seconds=session_timeout_seconds)

        ws_url, headers = browser_client.generate_ws_headers()
        live_view_url = browser_client.generate_live_view_url(expires=300)

        logger.warning(f"Session ID: {browser_client.session_id}")

        ssm_key = browser_client.session_id
        ssm_value = {
            "ws_url" : ws_url,
            "ws_headers" : headers,
            "live_view_url" : live_view_url
        }

        # Write to Parameter Store
        param_manager = ParameterStoreManager(aws_region)
        param_manager.put_parameter(f"/browser-session/{ssm_key}", ssm_value)

        # Debug information
        session_info = {
            "success": True,
            "status": "Browser session initialized successfully",
            "session_id" : browser_client.session_id
        }
        
        return session_info

    
    def _close_browser_session(self, aws_region, session_id) -> dict:
        """Close the current browser session"""
        browser_client = BrowserClient(aws_region)
        browser_client.client.stop_browser_session(browserIdentifier="aws.browser.v1",sessionId=session_id)
        
        # Delete from Parameter Store
        param_manager = ParameterStoreManager(aws_region)
        param_manager.delete_parameter(f"/browser-session/{session_id}")
        
        return {
            "success": True,
            "status": "Browser session stop successfully",
            "session_id" : session_id
        }

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        function_name = action = tool_parameters.get("function_name")
        session_id = tool_parameters.get("session_id")
        session_timeout_seconds = tool_parameters.get("session_timeout_seconds", None)
        aws_region = tool_parameters.get("aws_region", "us-east-1")

        if function_name == "init_browser_session":
            result = self._init_browser_session(aws_region, session_timeout_seconds)

        elif function_name == "close_browser_session":
            logger.warning(f"close_browser_session....")

            if not session_id:
                raise InvokeError("session_id is None, you should specify the session_id to close")

            result = self._close_browser_session(aws_region, session_id)

        else:
            raise InvokeError(f"unsupported function name - {function_name} ")
            
        
        yield self.create_json_message(result)
            

