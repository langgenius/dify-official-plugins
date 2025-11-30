from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

try:
    from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
except ImportError:
    raise ImportError("Please install simple-salesforce: pip install simple-salesforce~=0.1.45")


class SendMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Send a message through Salesforce Chatter (create a feed item)
        """
        # Get parameters
        message_text = tool_parameters.get("message_text", "")
        parent_id = tool_parameters.get("parent_id")
        feed_type = tool_parameters.get("feed_type", "TextPost")
        link_url = tool_parameters.get("link_url")
        title = tool_parameters.get("title")
        
        # Validate required parameters
        if not message_text:
            yield self.create_text_message("Message text is required to send a message.")
            return
        
        try:
            # Get credentials
            username = self.runtime.credentials.get("username")
            password = self.runtime.credentials.get("password")
            security_token = self.runtime.credentials.get("security_token")
            domain = self.runtime.credentials.get("domain")
            
            if not username or not password or not security_token:
                yield self.create_text_message("Salesforce credentials are not properly configured.")
                return
            
            # Connect to Salesforce
            try:
                sf = Salesforce(
                    username=username,
                    password=password,
                    security_token=security_token,
                    domain=domain if domain else None
                )
            except SalesforceAuthenticationFailed as e:
                yield self.create_text_message(f"Authentication failed: {str(e)}")
                return
            except Exception as e:
                yield self.create_text_message(f"Failed to connect to Salesforce: {str(e)}")
                return
            
            # If no parent_id is provided, get the current user's ID
            if not parent_id:
                try:
                    user_info = sf.query("SELECT Id FROM User WHERE Username = '{}'".format(username))
                    if user_info.get('totalSize', 0) > 0:
                        parent_id = user_info['records'][0]['Id']
                    else:
                        yield self.create_text_message("Could not determine current user ID. Please provide a parent_id.")
                        return
                except Exception as e:
                    yield self.create_text_message(f"Error getting user information: {str(e)}")
                    return
            
            # Prepare feed item data
            feed_item_data = {
                'ParentId': parent_id,
                'Body': message_text,
                'Type': feed_type
            }
            
            # Add optional fields for LinkPost
            if feed_type == 'LinkPost' and link_url:
                feed_item_data['LinkUrl'] = link_url
                
            if title:
                feed_item_data['Title'] = title
            
            # Create the feed item
            try:
                result = sf.FeedItem.create(feed_item_data)
                
                if result.get('success'):
                    feed_item_id = result.get('id')
                    
                    # Fetch the created feed item details
                    try:
                        feed_item_details = sf.FeedItem.get(feed_item_id)
                        
                        # Create response
                        response = {
                            "success": True,
                            "feed_item_id": feed_item_id,
                            "parent_id": feed_item_details.get('ParentId'),
                            "body": feed_item_details.get('Body'),
                            "type": feed_item_details.get('Type'),
                            "created_date": feed_item_details.get('CreatedDate'),
                            "created_by_id": feed_item_details.get('CreatedById')
                        }
                        
                        # Add link info if available
                        if feed_item_details.get('LinkUrl'):
                            response['link_url'] = feed_item_details.get('LinkUrl')
                        
                        if feed_item_details.get('Title'):
                            response['title'] = feed_item_details.get('Title')
                        
                        summary = f"Message posted successfully to Salesforce Chatter! Feed Item ID: {feed_item_id}"
                        yield self.create_text_message(summary)
                        yield self.create_json_message(response)
                        
                    except Exception as e:
                        # Feed item was created but couldn't fetch details
                        yield self.create_text_message(f"Message posted with ID: {feed_item_id}, but couldn't fetch details: {str(e)}")
                        yield self.create_json_message({"success": True, "feed_item_id": feed_item_id})
                else:
                    # Feed item creation failed
                    errors = result.get('errors', [])
                    error_msg = ", ".join([f"{err.get('message', 'Unknown error')}" for err in errors])
                    yield self.create_text_message(f"Failed to post message: {error_msg}")
                    return
                    
            except Exception as e:
                # Check if it's a permission issue
                error_str = str(e)
                if 'insufficient access rights' in error_str.lower():
                    yield self.create_text_message(
                        "Permission denied: Your Salesforce user doesn't have permission to post to Chatter. "
                        "Please ensure Chatter is enabled for your organization and your user has the necessary permissions."
                    )
                elif 'invalid field' in error_str.lower():
                    yield self.create_text_message(
                        f"Invalid field in request. This might be due to Chatter not being enabled or API version compatibility. Error: {error_str}"
                    )
                else:
                    yield self.create_text_message(f"Error posting message: {error_str}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Unexpected error: {str(e)}")
            return

