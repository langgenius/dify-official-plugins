import json
import logging
from collections.abc import Generator
from typing import Any, Dict
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

# Import the base functionality
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import AgentCore Memory SDK directly
try:
    from bedrock_agentcore.memory import MemoryClient
    AGENTCORE_SDK_AVAILABLE = True
except ImportError as e:
    AGENTCORE_SDK_AVAILABLE = False
    MemoryClient = None
    print(f"Warning: bedrock-agentcore SDK import failed: {e}")

logger = logging.getLogger(__name__)


class AgentCoreMemorySearchTool(Tool):
    memory_client: Any = None
    
    def _clean_id_parameter(self, value: str) -> str:
        """Clean ID parameter by removing surrounding quotes if present"""
        if value and isinstance(value, str):
            # Remove surrounding quotes if present
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
        return value
    
    def _initialize_memory_client(self, tool_parameters: dict[str, Any]) -> bool:
        """Initialize Memory client with AWS credentials"""
        try:
            # Get AWS credentials from tool parameters
            aws_region = tool_parameters.get("aws_region")
            aws_access_key_id = tool_parameters.get("aws_access_key_id")
            aws_secret_access_key = tool_parameters.get("aws_secret_access_key")

            # Initialize MemoryClient with region
            region = aws_region or 'us-east-1'
            
            if AGENTCORE_SDK_AVAILABLE:
                # Only add credentials if both access key and secret key are provided
                if aws_access_key_id and aws_secret_access_key:
                    # For MemoryClient, we need to set environment variables or use boto3 session
                    import os
                    os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
                    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
                    os.environ['AWS_REGION'] = region
                
                # Initialize MemoryClient
                self.memory_client = MemoryClient(region_name=region)
                logger.info(f"Memory client initialized for region: {region}")
                return True
            else:
                logger.error("AgentCore Memory SDK not available")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize Memory client: {str(e)}")
            return False
    
    def _search_memories(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Search for relevant memories"""
        try:
            # Extract business parameters
            search_query = tool_parameters.get('search_query', 'all')
            max_results = tool_parameters.get('max_results', 10)
            memory_id = self._clean_id_parameter(tool_parameters.get('memory_id', ''))
            namespace = tool_parameters.get('namespace', '/')
            
            # Use "all" as default search query if not provided
            if not search_query or search_query.strip() == '':
                search_query = 'all'
            
            # Use "/" as default namespace if not provided (Global across all strategies)
            if not namespace or namespace.strip() == '':
                namespace = '/'
            
            if not memory_id:
                yield self.create_text_message("Error: Memory ID is required for search operation")
                return
            
            # Validate max_results
            if max_results < 1 or max_results > 20:
                max_results = 10
            
            yield self.create_text_message(f"🔍 Searching memories for: '{search_query}' in namespace: '{namespace}'")
            
            if self.memory_client:
                # Search memories using retrieve_memories method
                # Note: actor_id is not required for search operation in some cases
                result = self.memory_client.retrieve_memories(
                    memory_id=memory_id,
                    query=search_query,
                    namespace=namespace,
                    top_k=max_results
                )
                
                # Extract memories from response
                memories_list = result.get('memories', []) if isinstance(result, dict) else result
                
                # Ensure it's a list
                if not isinstance(memories_list, list):
                    memories_list = list(memories_list) if hasattr(memories_list, '__iter__') else []
                
                # Apply max_results limit if needed
                if max_results and len(memories_list) > max_results:
                    memories_list = memories_list[:max_results]
                
                # Process memories to ensure JSON serialization
                processed_memories = []
                for memory in memories_list:
                    if isinstance(memory, dict):
                        # Convert datetime objects to strings
                        processed_memory = {}
                        for key, value in memory.items():
                            if hasattr(value, 'isoformat'):  # datetime object
                                processed_memory[key] = value.isoformat()
                            else:
                                processed_memory[key] = value
                        processed_memories.append(processed_memory)
                    else:
                        processed_memories.append(str(memory))
                
                # Format response with detailed information
                response_data = {
                    'success': True,
                    'message': f"Found {len(processed_memories)} relevant memor(ies)",
                    'data': {
                        'memories_count': len(processed_memories),
                        'memory_id': memory_id,
                        'namespace': namespace,
                        'query': search_query,
                        'memories': processed_memories
                    }
                }
                
                # Use consistent JSON response format
                yield self.create_json_message(response_data)
            else:
                yield self.create_text_message("❌ AgentCore Memory SDK not available")
                
        except Exception as e:
            logger.error(f"Search memories error: {str(e)}")
            yield self.create_text_message(f"Exception in search operation: {str(e)}")

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        invoke tools
        """
        try:
            # Initialize Memory client if not already initialized
            if not self.memory_client:
                if not self._initialize_memory_client(tool_parameters):
                    yield self.create_text_message("❌ Failed to initialize AgentCore Memory client")
                    return

            # This tool only performs search operation
            yield from self._search_memories(tool_parameters)

        except Exception as e:
            logger.error(f"Invoke error: {str(e)}", exc_info=True)
            yield self.create_text_message(f"❌ Internal error: {str(e)}")