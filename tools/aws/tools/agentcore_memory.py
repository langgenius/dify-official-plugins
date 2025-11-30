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


class AgentCoreMemoryTool(Tool):
    memory_client: Any = None
    memory_id: str = None
    actor_id: str = None
    session_id: str = None
    
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
    
    def _create_new_memory_resource(self, tool_parameters: dict[str, Any]) -> tuple[str, str, str]:
        """Create new memory resource and return memory_id, actor_id, session_id"""
        try:
            # Default strategies for new memory resources
            default_strategies = [
                {
                    'semanticMemoryStrategy':
                        {
                            'name':'semanticMemory',
                            "namespaces": ["/semantic/{actorId}/{sessionId}"]
                            }
                        },
                {
                    'summaryMemoryStrategy': 
                        {
                            'name': 'summaryMemory',
                            "namespaces": ["/summaries/{actorId}/{sessionId}"]
                            }
                        },
                {
                    'userPreferenceMemoryStrategy': 
                        {
                            'name': 'userPreferenceMemory',
                            "namespaces": ["/userPreference/{actorId}/{sessionId}"]
                            }
                }
            ]
            
            # Generate unique identifiers
            import uuid
            import time
            
            timestamp = int(time.time())
            # Memory name must match pattern [a-zA-Z][a-zA-Z0-9_]{0,47}
            memory_name = f"autoMemory_{timestamp}"
            actor_id = f"actor_{uuid.uuid4().hex[:8]}"
            session_id = f"session_{uuid.uuid4().hex[:8]}"
            
            # Create memory resource
            result = self.memory_client.create_memory_and_wait(
                name=memory_name,
                description="Auto-created memory resource",
                strategies=default_strategies
            )
            
            memory_id = result.get('memoryId', 'unknown')
            
            logger.info(f"Created new memory resource: {memory_id}, actor: {actor_id}, session: {session_id}")
            
            return memory_id, actor_id, session_id
            
        except Exception as e:
            logger.error(f"Failed to create memory resource: {str(e)}")
            raise
    

    
    def _record_information(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Record information to memory"""
        try:
            # Extract the information to record
            information = tool_parameters.get('information', '')
            
            if not information:
                yield self.create_text_message("Error: Information to record is required")
                return
            
            # Use instance variables
            memory_id = self.memory_id
            actor_id = self.actor_id
            session_id = self.session_id
            
            yield self.create_text_message(f"💾 Recording information for {actor_id}...")
            
            if self.memory_client:
                # Format messages for storage
                messages = [
                    (information, "USER"),
                    ("Information recorded successfully.", "ASSISTANT")
                ]
                
                # Store conversation event
                result = self.memory_client.create_event(
                    memory_id=memory_id,
                    actor_id=actor_id,
                    session_id=session_id,
                    messages=messages
                )
                
                # Extract event ID from result
                event_id = "unknown"
                if isinstance(result, dict):
                    if 'event' in result:
                        event_id = result['event'].get('eventId', 'unknown')
                    elif 'eventId' in result:
                        event_id = result['eventId']
                
                # Format response as text message
                response_text = f"✅ Information recorded successfully!\n\nEvent ID: {event_id}\nMemory ID: {memory_id}\nActor ID: {actor_id}\nSession ID: {session_id}\nInformation length: {len(information)} characters"
                
                yield self.create_text_message(response_text)
            else:
                yield self.create_text_message("❌ AgentCore Memory SDK not available")
                
        except Exception as e:
            logger.error(f"Record information error: {str(e)}")
            yield self.create_text_message(f"Exception in record operation: {str(e)}")
    
    def _retrieve_history(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Retrieve conversation history using get_last_k_turns"""
        try:
            # Extract business parameters
            k = tool_parameters.get('max_results', 10)
            
            # Validate k (number of turns to retrieve)
            if k < 1 or k > 50:
                k = 10
            
            # Use instance variables
            memory_id = self.memory_id
            actor_id = self.actor_id
            session_id = self.session_id
            
            yield self.create_text_message(f"📚 Retrieving last {k} conversation turns for {actor_id} (session: {session_id})")
            
            if self.memory_client:
                # Retrieve last k conversation turns using get_last_k_turns
                events = self.memory_client.get_last_k_turns(
                    memory_id=memory_id,
                    actor_id=actor_id,
                    session_id=session_id,
                    k=k
                )
                
                # Format the events for better readability
                formatted_events = []
                
                if events and isinstance(events, list):
                    for i, event in enumerate(events):
                        # Each event is actually a list of messages
                        if isinstance(event, list):
                            formatted_event = {
                                'turn_number': i + 1,
                                'event_id': f'turn_{i+1}',
                                'timestamp': 'unknown',
                                'messages': event
                            }
                        elif isinstance(event, dict):
                            # Fallback for dict format
                            formatted_event = {
                                'turn_number': i + 1,
                                'event_id': event.get('eventId', f'turn_{i+1}'),
                                'timestamp': event.get('timestamp', 'unknown'),
                                'messages': event.get('messages', [])
                            }
                        else:
                            # Handle event objects with attributes
                            formatted_event = {
                                'turn_number': i + 1,
                                'event_id': getattr(event, 'eventId', f'turn_{i+1}'),
                                'timestamp': getattr(event, 'timestamp', 'unknown'),
                                'messages': getattr(event, 'messages', [])
                            }
                        formatted_events.append(formatted_event)
                
                # Format response
                response_data = {
                    'success': True,
                    'message': f"Retrieved last {len(formatted_events)} conversation turns successfully",
                    'data': {
                        'memory_id': memory_id,
                        'actor_id': actor_id,
                        'session_id': session_id,
                        'turns_requested': k,
                        'turns_retrieved': len(formatted_events),
                        'conversation_turns': formatted_events
                    }
                }
                
                yield self.create_json_message(response_data)
            else:
                yield self.create_text_message("❌ AgentCore Memory SDK not available")
                
        except Exception as e:
            logger.error(f"Retrieve history error: {str(e)}")
            yield self.create_text_message(f"Exception in retrieve operation: {str(e)}")

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        invoke tools
        """
        try:
            # Check operation first
            operation = tool_parameters.get("operation")
            if not operation:
                yield self.create_text_message("❌ Please select an operation (record/retrieve)")
                return
            
            if operation not in ['record', 'retrieve']:
                yield self.create_text_message(f"❌ Invalid operation: {operation}. Must be 'record' or 'retrieve'")
                return
            
            # Initialize Memory client if not already initialized
            if not self.memory_client:
                if not self._initialize_memory_client(tool_parameters):
                    yield self.create_text_message("❌ Failed to initialize AgentCore Memory client")
                    return

            # Get and clean parameters like agentcore_memory_search.py
            memory_id = tool_parameters.get("memory_id", "").strip().strip('"\'')
            actor_id = tool_parameters.get("actor_id", "").strip().strip('"\'')
            session_id = tool_parameters.get("session_id", "").strip().strip('"\'') 
            
            # If any required parameter is missing, create new ones
            if not memory_id or not actor_id or not session_id:
                yield self.create_text_message("🏗️ Creating new memory resource...")
                try:
                    memory_id, actor_id, session_id = self._create_new_memory_resource(tool_parameters)
                    yield self.create_text_message(f"✅ New memory resource created!\n\nMemory ID: {memory_id}\nActor ID: {actor_id}\nSession ID: {session_id}")
                    
                    # Return the generated IDs in JSON format
                    creation_data = {
                        'memory_id': memory_id,
                        'actor_id': actor_id,
                        'session_id': session_id
                    }
                    yield self.create_json_message(creation_data)
                except Exception as e:
                    yield self.create_text_message(f"❌ Failed to create memory resource: {str(e)}")
                    return
            
            # Set instance variables
            self.memory_id = memory_id
            self.actor_id = actor_id
            self.session_id = session_id
            
            # Route to appropriate operation
            if operation == 'record':
                yield from self._record_information(tool_parameters)
            elif operation == 'retrieve':
                yield from self._retrieve_history(tool_parameters)

        except Exception as e:
            logger.error(f"Invoke error: {str(e)}", exc_info=True)
            yield self.create_text_message(f"❌ Internal error: {str(e)}")