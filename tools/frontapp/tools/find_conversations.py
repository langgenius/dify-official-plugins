import json
from collections.abc import Generator
from typing import Any, Optional
from datetime import datetime, timedelta

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.invoke_message import InvokeMessage


class FindConversationsTool(Tool):
    """
    Tool for finding and filtering conversations in Front API
    """
    
    def _invoke(self, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        """
        Find and filter conversations through Front API
        
        Args:
            tool_parameters: Dictionary containing search and filter parameters
            
        Yields:
            ToolInvokeMessage: Various message types to communicate results
        """
        # 1. PARAMETER EXTRACTION AND VALIDATION
        search_query = tool_parameters.get("search_query", "")
        status_filter = tool_parameters.get("status_filter", "")
        inbox_id = tool_parameters.get("inbox_id", "")
        tag_ids = tool_parameters.get("tag_ids", [])
        assignee_id = tool_parameters.get("assignee_id", "")
        limit = tool_parameters.get("limit", 50)
        sort_by = tool_parameters.get("sort_by", "date")
        sort_order = tool_parameters.get("sort_order", "desc")
        
        # Date range parameters
        date_after = tool_parameters.get("date_after", "")
        date_before = tool_parameters.get("date_before", "")
        
        # 2. CREDENTIAL HANDLING
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message("Front API access token is required. Please configure OAuth authentication.")
            return
            
        access_token = self.runtime.credentials.get("access_token")
        
        # 3. LOG THE OPERATION START
        operation_log = self.create_log_message(
            label="Conversation Search Started",
            data={
                "search_query": search_query,
                "status_filter": status_filter,
                "inbox_id": inbox_id,
                "limit": limit,
                "sort_by": sort_by,
                "sort_order": sort_order
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
            
            # Build query parameters
            params = {}
            
            # Search query
            if search_query:
                params["q"] = search_query
                
            # Status filter
            if status_filter:
                params["status"] = status_filter
                
            # Inbox filter
            if inbox_id:
                params["inbox_id"] = inbox_id
                
            # Assignee filter
            if assignee_id:
                params["assignee_id"] = assignee_id
                
            # Tag filters
            if tag_ids:
                if isinstance(tag_ids, list):
                    params["tag_ids"] = ",".join(tag_ids)
                else:
                    params["tag_ids"] = tag_ids
            
            # Date filters
            if date_after:
                params["after"] = date_after
                
            if date_before:
                params["before"] = date_before
            
            # Pagination and sorting
            params["limit"] = min(limit, 100)  # Front API limit
            params["sort_by"] = sort_by
            params["sort_order"] = sort_order
            
            # 5. MAKE API CALL TO GET CONVERSATIONS
            api_log = self.create_log_message(
                label="API Call - Get Conversations",
                data={"endpoint": "conversations", "params": params},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
                parent=operation_log
            )
            yield api_log
            
            response = requests.get(
                "https://api2.frontapp.com/conversations",
                headers=headers,
                params=params,
                timeout=30
            )
            
            # 6. HANDLE RESPONSE
            if response.status_code == 200:
                data = response.json()
                conversations = data.get("_results", [])
                
                yield self.create_json_message(data)
                
                # Process and format results
                if conversations:
                    processed_conversations = []
                    
                    for conv in conversations:
                        processed_conv = {
                            "id": conv.get("id"),
                            "subject": conv.get("subject", "No subject"),
                            "status": conv.get("status"),
                            "created_at": conv.get("created_at"),
                            "last_message_at": conv.get("last_message").get("created_at") if conv.get("last_message") else None,
                            "assignee": conv.get("assignee", {}).get("display_name") if conv.get("assignee") else "Unassigned",
                            "tags": [tag.get("name") for tag in conv.get("tags", [])],
                            "inbox": conv.get("inbox", {}).get("name"),
                            "recipient": self._extract_recipient_from_conversation(conv),
                            "message_count": len(conv.get("_links", {}).get("related", {}).get("messages", []))
                        }
                        processed_conversations.append(processed_conv)
                    
                    # Create summary
                    summary = {
                        "total_found": len(conversations),
                        "search_query": search_query,
                        "filters_applied": {
                            "status": status_filter,
                            "inbox_id": inbox_id,
                            "assignee_id": assignee_id,
                            "tags": tag_ids,
                            "date_range": f"{date_after} to {date_before}" if date_after or date_before else None
                        },
                        "conversations": processed_conversations
                    }
                    
                    yield self.create_variable_message("conversation_results", summary)
                    
                    # Create human-readable summary
                    status_counts = {}
                    inbox_counts = {}
                    
                    for conv in processed_conversations:
                        status = conv["status"]
                        inbox = conv["inbox"]
                        
                        status_counts[status] = status_counts.get(status, 0) + 1
                        inbox_counts[inbox] = inbox_counts.get(inbox, 0) + 1
                    
                    summary_text = f"Found {len(conversations)} conversations"
                    if search_query:
                        summary_text += f" matching '{search_query}'"
                    
                    summary_text += f"\n\nStatus breakdown:"
                    for status, count in status_counts.items():
                        summary_text += f"\n- {status}: {count}"
                    
                    summary_text += f"\n\nInbox breakdown:"
                    for inbox, count in inbox_counts.items():
                        summary_text += f"\n- {inbox or 'Unknown'}: {count}"
                    
                    yield self.create_text_message(summary_text)
                    
                    # Show top 5 conversations
                    if processed_conversations:
                        top_convs_text = "\n\nTop conversations:"
                        for i, conv in enumerate(processed_conversations[:5]):
                            top_convs_text += f"\n{i+1}. {conv['subject'][:50]}..."
                            top_convs_text += f"\n   Status: {conv['status']}, Assignee: {conv['assignee']}"
                            if conv['tags']:
                                top_convs_text += f", Tags: {', '.join(conv['tags'])}"
                        
                        yield self.create_text_message(top_convs_text)
                
                else:
                    yield self.create_text_message("No conversations found matching the specified criteria.")
                    yield self.create_variable_message("conversation_results", {
                        "total_found": 0,
                        "search_query": search_query,
                        "filters_applied": {
                            "status": status_filter,
                            "inbox_id": inbox_id,
                            "assignee_id": assignee_id,
                            "tags": tag_ids
                        },
                        "conversations": []
                    })
                
            else:
                # Handle API errors
                error_msg = f"Failed to fetch conversations: HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f" - {error_data.get('message', 'Unknown error')}"
                except:
                    error_msg += f" - {response.text}"
                
                yield self.create_log_message(
                    label="API Error",
                    data={
                        "status_code": response.status_code,
                        "error": response.text[:200]
                    },
                    status=InvokeMessage.LogMessage.LogStatus.ERROR
                )
                yield self.create_text_message(error_msg)
                
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
        """
        Extract recipient information from conversation data
        """
        try:
            # Try to get recipient from last message
            last_message = conversation.get("last_message", {})
            recipients = last_message.get("recipients", [])
            
            if recipients:
                # Return first recipient's email or name
                first_recipient = recipients[0]
                return first_recipient.get("handle") or first_recipient.get("name")
            
            # Fallback to conversation recipient if available
            recipient = conversation.get("recipient")
            if recipient:
                return recipient.get("handle") or recipient.get("name")
                
            return None
            
        except Exception:
            return None