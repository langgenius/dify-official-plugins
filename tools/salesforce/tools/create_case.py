from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

try:
    from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
except ImportError:
    raise ImportError("Please install simple-salesforce: pip install simple-salesforce~=0.1.45")


class CreateCaseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a new case in Salesforce
        """
        # Get parameters
        subject = tool_parameters.get("subject", "")
        description = tool_parameters.get("description", "")
        priority = tool_parameters.get("priority", "Medium")
        status = tool_parameters.get("status", "New")
        origin = tool_parameters.get("origin")
        contact_id = tool_parameters.get("contact_id")
        account_id = tool_parameters.get("account_id")
        
        # Validate required parameters
        if not subject:
            yield self.create_text_message("Subject is required to create a case.")
            return
        
        if not description:
            yield self.create_text_message("Description is required to create a case.")
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
            
            # Prepare case data
            case_data = {
                'Subject': subject,
                'Description': description,
                'Priority': priority,
                'Status': status
            }
            
            # Add optional fields if provided
            if origin:
                case_data['Origin'] = origin
            
            if contact_id:
                case_data['ContactId'] = contact_id
            
            if account_id:
                case_data['AccountId'] = account_id
            
            # Create the case
            try:
                result = sf.Case.create(case_data)
                
                if result.get('success'):
                    case_id = result.get('id')
                    
                    # Fetch the created case details
                    try:
                        case_details = sf.Case.get(case_id)
                        
                        # Create response
                        response = {
                            "success": True,
                            "case_id": case_id,
                            "case_number": case_details.get('CaseNumber'),
                            "subject": case_details.get('Subject'),
                            "description": case_details.get('Description'),
                            "priority": case_details.get('Priority'),
                            "status": case_details.get('Status'),
                            "origin": case_details.get('Origin'),
                            "created_date": case_details.get('CreatedDate')
                        }
                        
                        # Add contact and account info if available
                        if case_details.get('ContactId'):
                            response['contact_id'] = case_details.get('ContactId')
                        
                        if case_details.get('AccountId'):
                            response['account_id'] = case_details.get('AccountId')
                        
                        summary = f"Case created successfully! Case Number: {response['case_number']}, Case ID: {case_id}"
                        yield self.create_text_message(summary)
                        yield self.create_json_message(response)
                        
                    except Exception as e:
                        # Case was created but couldn't fetch details
                        yield self.create_text_message(f"Case created with ID: {case_id}, but couldn't fetch details: {str(e)}")
                        yield self.create_json_message({"success": True, "case_id": case_id})
                else:
                    # Case creation failed
                    errors = result.get('errors', [])
                    error_msg = ", ".join([f"{err.get('message', 'Unknown error')}" for err in errors])
                    yield self.create_text_message(f"Failed to create case: {error_msg}")
                    return
                    
            except Exception as e:
                yield self.create_text_message(f"Error creating case: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Unexpected error: {str(e)}")
            return

