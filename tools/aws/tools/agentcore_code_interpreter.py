from collections.abc import Generator
from typing import Any
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
import boto3
import json
import time

class AgentcoreCodeInterpreterTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        result = self.execute(**tool_parameters)
        yield self.create_json_message(result)


    def execute(self, language=None, code=None, command=None, session_id=None, code_interpreter_id=None, aws_ak=None, aws_sk=None, aws_region=None, **kwargs):
        error_msg = ""
        
        try:
            # 1. Create clients based on provided AWS credentials
            data_client = self.create_client(aws_ak, aws_sk, aws_region, 'bedrock-agentcore')
            
            # 2. Get or create code interpreter
            if not code_interpreter_id:
                control_client = self.create_client(aws_ak, aws_sk, aws_region, 'bedrock-agentcore-control')
                code_interpreter_id = self.create_code_interpreter(control_client)
            
            # 3. Get or create session
            if not session_id:
                session_id = self.init_session(data_client, code_interpreter_id)
            
            # 4. Execute command first if provided, then code
            results = []
            
            if command:
                command_result = self.exec_command_internal(data_client, code_interpreter_id, session_id, command)
                results.append({"type": "command", "result": command_result})
            
            if code and language:
                code_result = self.exec_code_internal(data_client, code_interpreter_id, session_id, language, code)
                results.append({"type": "code", "result": code_result})
            
            if not command and not code:
                raise ValueError("Either command or code must be provided")
                
        except Exception as e:
            error_msg = str(e)
        
        if error_msg:
            result = {"status": "error", "reason": str(error_msg)}
        else:
            result = {
                "status": "success", 
                "session_id": session_id, 
                "code_interpreter_id": code_interpreter_id,
                "results": results
            }
        
        return result

    def create_client(self, aws_ak=None, aws_sk=None, aws_region=None, service_name='bedrock-agentcore'):
        """Create AWS client with or without provided credentials"""
        if aws_ak and aws_sk and aws_region:
            return boto3.client(service_name, 
                              aws_access_key_id=aws_ak, 
                              aws_secret_access_key=aws_sk, 
                              region_name=aws_region)
        else:
            return boto3.client(service_name)

    def create_code_interpreter(self, client):
        """Create a new code interpreter"""
        timestamp = int(time.time())
        response = client.create_code_interpreter(
            name=f'code_interpreter_{timestamp}',
            description='code-interpreter with network access',
            networkConfiguration={'networkMode': 'PUBLIC'}
        )
        return response.get('codeInterpreterId')

    def exec_code_internal(self, client, code_interpreter_id, session_id, language, code):
        """Execute code in the code interpreter"""
        arguments = {
            "language": language,
            "code": code
        }
        response = client.invoke_code_interpreter(
            codeInterpreterIdentifier=code_interpreter_id,
            name="executeCode",
            sessionId=session_id,
            arguments=arguments
        )
        return self.get_tool_result(response)

    def exec_command_internal(self, client, code_interpreter_id, session_id, command):
        """Execute command in the code interpreter"""
        arguments = {
            "command": command
        }
        response = client.invoke_code_interpreter(
            codeInterpreterIdentifier=code_interpreter_id,
            name="executeCommand",
            sessionId=session_id,
            arguments=arguments
        )
        return self.get_tool_result(response)


    def init_session(self, data_client, ci_id):
        try:
            response = data_client.start_code_interpreter_session(codeInterpreterIdentifier=ci_id, sessionTimeoutSeconds=900)
            session_id = response['sessionId']
        except Exception as e:
            raise
        return session_id


    def get_tool_result(self, response):
        try:
            if "stream" in response:
                event_stream = response["stream"]
                for event in event_stream:
                    if "result" in event:
                        result = event["result"]
                        return str(result)
        except Exception as e:
            return f"tool result error: {e}"