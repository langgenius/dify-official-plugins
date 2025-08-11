import json
from collections.abc import Generator
from typing import Any, Optional

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.invoke_message import InvokeMessage


class FindChannelsTool(Tool):
    """
    Tool for finding and filtering channels and conversations in Front API
    """
    
    def _invoke(self, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        """
        Find channels and optionally their conversations through Front API
        
        Args:
            tool_parameters: Dictionary containing search and filter parameters
            
        Yields:
            ToolInvokeMessage: Various message types to communicate results
        """
        # 1. PARAMETER EXTRACTION AND VALIDATION
        search_type = tool_parameters.get("search_type", "channels")
        channel_type_filter = tool_parameters.get("channel_type_filter", "")
        channel_name_search = tool_parameters.get("channel_name_search", "")
        include_conversations = tool_parameters.get("include_conversations", False)
        conversation_status = tool_parameters.get("conversation_status", "")
        limit = tool_parameters.get("limit", 50)
        
        # 2. CREDENTIAL HANDLING
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message("Front API access token is required. Please configure OAuth authentication.")
            return
            
        access_token = self.runtime.credentials.get("access_token")
        
        # 3. LOG THE OPERATION START
        operation_log = self.create_log_message(
            label="Channel/Conversation Search Started",
            data={
                "search_type": search_type,
                "channel_type_filter": channel_type_filter,
                "channel_name_search": channel_name_search,
                "include_conversations": include_conversations,
                "limit": limit
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS
        )
        yield operation_log
        
        try:
            # 4. PREPARE API REQUEST
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
            
            # 5. FETCH CHANNELS
            api_log = self.create_log_message(
                label="API Call - Get Channels",
                data={"endpoint": "channels"},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
                parent=operation_log
            )
            yield api_log
            
            channels_response = requests.get(
                "https://api2.frontapp.com/channels",
                headers=headers,
                timeout=30
            )
            
            if channels_response.status_code != 200:
                error_msg = f"Failed to fetch channels: HTTP {channels_response.status_code}"
                try:
                    error_data = channels_response.json()
                    error_msg += f" - {error_data.get('message', 'Unknown error')}"
                except:
                    error_msg += f" - {channels_response.text}"
                
                yield self.create_text_message(error_msg)
                return
            
            channels_data = channels_response.json()
            all_channels = channels_data.get("_results", [])
            
            # 6. FILTER CHANNELS
            filtered_channels = []
            
            for channel in all_channels:
                # Apply channel type filter
                if channel_type_filter and channel.get("type") != channel_type_filter:
                    continue
                
                # Apply channel name search
                if channel_name_search:
                    channel_name = channel.get("name", "").lower()
                    if channel_name_search.lower() not in channel_name:
                        continue
                
                filtered_channels.append(channel)
            
            # Limit results
            if limit and limit > 0:
                filtered_channels = filtered_channels[:limit]
            
            # 7. PROCESS CHANNEL RESULTS
            processed_channels = []
            
            for channel in filtered_channels:
                processed_channel = {
                    "id": channel.get("id"),
                    "name": channel.get("name"),
                    "type": channel.get("type"),
                    "address": channel.get("address"),
                    "send_as": channel.get("send_as"),
                    "settings": channel.get("settings", {}),
                    "is_private": channel.get("is_private", False),
                    "conversations": []
                }
                
                # 8. FETCH CONVERSATIONS FOR EACH CHANNEL IF REQUESTED
                if include_conversations and search_type in ["channels", "both"]:
                    conv_log = self.create_log_message(
                        label=f"Fetching conversations for channel: {channel.get('name')}",
                        data={"channel_id": channel.get("id")},
                        status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
                        parent=operation_log
                    )
                    yield conv_log
                    
                    # Get conversations for this channel
                    conv_params = {"limit": 20}  # Limit conversations per channel
                    if conversation_status:
                        conv_params["status"] = conversation_status
                    
                    try:
                        conv_response = requests.get(
                            f"https://api2.frontapp.com/channels/{channel.get('id')}/conversations",
                            headers=headers,
                            params=conv_params,
                            timeout=15
                        )
                        
                        if conv_response.status_code == 200:
                            conv_data = conv_response.json()
                            conversations = conv_data.get("_results", [])
                            
                            for conv in conversations:
                                processed_conv = {
                                    "id": conv.get("id"),
                                    "subject": conv.get("subject", "No subject"),
                                    "status": conv.get("status"),
                                    "created_at": conv.get("created_at"),
                                    "assignee": conv.get("assignee", {}).get("display_name") if conv.get("assignee") else "Unassigned",
                                    "tags": [tag.get("name") for tag in conv.get("tags", [])]
                                }
                                processed_channel["conversations"].append(processed_conv)
                    
                    except Exception as e:
                        # Continue even if conversation fetch fails
                        processed_channel["conversation_error"] = str(e)
                
                processed_channels.append(processed_channel)
            
            # 9. FETCH STANDALONE CONVERSATIONS IF REQUESTED
            all_conversations = []
            if search_type in ["conversations", "both"]:
                conv_params = {"limit": limit or 50}
                if conversation_status:
                    conv_params["status"] = conversation_status
                
                conv_api_log = self.create_log_message(
                    label="API Call - Get All Conversations",
                    data={"endpoint": "conversations", "params": conv_params},
                    status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
                    parent=operation_log
                )
                yield conv_api_log
                
                try:
                    all_conv_response = requests.get(
                        "https://api2.frontapp.com/conversations",
                        headers=headers,
                        params=conv_params,
                        timeout=30
                    )
                    
                    if all_conv_response.status_code == 200:
                        all_conv_data = all_conv_response.json()
                        conversations = all_conv_data.get("_results", [])
                        
                        for conv in conversations:
                            processed_conv = {
                                "id": conv.get("id"),
                                "subject": conv.get("subject", "No subject"),
                                "status": conv.get("status"),
                                "created_at": conv.get("created_at"),
                                "last_message_at": conv.get("last_message", {}).get("created_at") if conv.get("last_message") else None,
                                "assignee": conv.get("assignee", {}).get("display_name") if conv.get("assignee") else "Unassigned",
                                "tags": [tag.get("name") for tag in conv.get("tags", [])],
                                "inbox": conv.get("inbox", {}).get("name") if conv.get("inbox") else "Unknown",
                                "recipient": self._extract_recipient_from_conversation(conv)
                            }
                            all_conversations.append(processed_conv)
                
                except Exception as e:
                    yield self.create_log_message(
                        label="Conversation Fetch Error",
                        data={"error": str(e)},
                        status=InvokeMessage.LogMessage.LogStatus.ERROR
                    )
            
            # 10. PREPARE RESULTS
            results = {
                "search_type": search_type,
                "filters_applied": {
                    "channel_type": channel_type_filter,
                    "channel_name_search": channel_name_search,
                    "conversation_status": conversation_status,
                    "include_conversations": include_conversations
                },
                "channels": processed_channels,
                "conversations": all_conversations,
                "summary": {
                    "total_channels_found": len(processed_channels),
                    "total_conversations_found": len(all_conversations),
                    "channel_types": {}
                }
            }
            
            # Calculate channel type breakdown
            for channel in processed_channels:
                ch_type = channel.get("type", "unknown")
                results["summary"]["channel_types"][ch_type] = results["summary"]["channel_types"].get(ch_type, 0) + 1
            
            yield self.create_json_message(results)
            yield self.create_variable_message("search_results", results)
            
            # 11. CREATE HUMAN-READABLE SUMMARY
            summary_text = f"Search Results:\n\n"
            
            if search_type in ["channels", "both"]:
                summary_text += f"📧 Channels Found: {len(processed_channels)}\n"
                if results["summary"]["channel_types"]:
                    summary_text += "Channel Types:\n"
                    for ch_type, count in results["summary"]["channel_types"].items():
                        summary_text += f"  - {ch_type}: {count}\n"
                
                if processed_channels:
                    summary_text += "\nTop Channels:\n"
                    for i, channel in enumerate(processed_channels[:5]):
                        summary_text += f"{i+1}. {channel['name']} ({channel['type']})\n"
                        if include_conversations and channel['conversations']:
                            summary_text += f"   └─ {len(channel['conversations'])} conversations\n"
            
            if search_type in ["conversations", "both"]:
                summary_text += f"\n💬 Conversations Found: {len(all_conversations)}\n"
                
                if all_conversations:
                    # Status breakdown
                    status_counts = {}
                    for conv in all_conversations:
                        status = conv["status"]
                        status_counts[status] = status_counts.get(status, 0) + 1
                    
                    summary_text += "Status Breakdown:\n"
                    for status, count in status_counts.items():
                        summary_text += f"  - {status}: {count}\n"
                    
                    summary_text += "\nRecent Conversations:\n"
                    for i, conv in enumerate(all_conversations[:5]):
                        summary_text += f"{i+1}. {conv['subject'][:50]}...\n"
                        summary_text += f"   Status: {conv['status']}, Assignee: {conv['assignee']}\n"
            
            yield self.create_text_message(summary_text)
                
        except requests.Timeout:
            yield self.create_text_message("Request timed out. Please try again.")
            
        except requests.RequestException as e:
            yield self.create_log_message(
                label="Network Error",
                data={"error": str(e)},
                status=InvokeMessage.LogMessage.LogStatus.ERROR
            )
            yield self.create_text_message(f"Network error occurred: {str(e)}")
            
        except Exception as e:
            # Handle unexpected errors
            yield self.create_log_message(
                label="Unexpected Error",
                data={"error": str(e), "type": type(e).__name__},
                status=InvokeMessage.LogMessage.LogStatus.ERROR
            )
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
    
    def _extract_recipient_from_conversation(self, conversation: dict) -> Optional[str]:
        """Extract recipient information from conversation data"""
        try:
            last_message = conversation.get("last_message", {})
            recipients = last_message.get("recipients", [])
            
            if recipients:
                first_recipient = recipients[0]
                return first_recipient.get("handle") or first_recipient.get("name")
            
            recipient = conversation.get("recipient")
            if recipient:
                return recipient.get("handle") or recipient.get("name")
                
            return None
            
        except Exception:
            return None