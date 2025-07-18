from collections.abc import Generator
from typing import Any
import re

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from hubspot import HubSpot
from hubspot.crm.contacts import SimplePublicObjectInputForCreate, ApiException

class CreateContactTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a new contact in HubSpot
        """
        # Get required parameter
        email = tool_parameters.get("email", "").strip()
        
        # Validate email
        if not email:
            yield self.create_text_message("Email address is required to create a contact.")
            return
            
        # Basic email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            yield self.create_text_message(f"Invalid email format: {email}")
            return
        
        # Get optional parameters
        firstname = tool_parameters.get("firstname", "").strip()
        lastname = tool_parameters.get("lastname", "").strip()
        phone = tool_parameters.get("phone", "").strip()
        company = tool_parameters.get("company", "").strip()
        jobtitle = tool_parameters.get("jobtitle", "").strip()
        
        try:
            # Get access token from credentials
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("HubSpot access token is required.")
                return
                
            # Create HubSpot client
            client = HubSpot(access_token=access_token)
            
            # Prepare contact properties
            properties = {
                "email": email
            }
            
            # Add optional properties if provided
            if firstname:
                properties["firstname"] = firstname
            if lastname:
                properties["lastname"] = lastname
            if phone:
                properties["phone"] = phone
            if company:
                properties["company"] = company
            if jobtitle:
                properties["jobtitle"] = jobtitle
            
            # Create contact object
            contact_input = SimplePublicObjectInputForCreate(properties=properties)
            
            try:
                # Create the contact
                api_response = client.crm.contacts.basic_api.create(
                    simple_public_object_input_for_create=contact_input
                )
                
                # Extract contact information
                contact = api_response.to_dict()
                contact_id = contact['id']
                created_at = contact['created_at']
                updated_at = contact['updated_at']
                
                # Get the actual properties from the response
                response_properties = contact.get('properties', {})
                
                # Create response data
                response_data = {
                    "id": contact_id,
                    "email": response_properties.get('email', email),
                    "firstname": response_properties.get('firstname', ''),
                    "lastname": response_properties.get('lastname', ''),
                    "phone": response_properties.get('phone', ''),
                    "company": response_properties.get('company', ''),
                    "jobtitle": response_properties.get('jobtitle', ''),
                    "created_at": created_at,
                    "updated_at": updated_at
                }
                
                # Create summary message
                name_parts = []
                if response_properties.get('firstname'):
                    name_parts.append(response_properties['firstname'])
                if response_properties.get('lastname'):
                    name_parts.append(response_properties['lastname'])
                
                if name_parts:
                    name = ' '.join(name_parts)
                    summary = f"Successfully created contact '{name}' ({email}) with ID: {contact_id}"
                else:
                    summary = f"Successfully created contact ({email}) with ID: {contact_id}"
                
                yield self.create_text_message(summary)
                yield self.create_json_message(response_data)
                
            except ApiException as e:
                error_body = e.body
                if "CONTACT_EXISTS" in str(error_body):
                    yield self.create_text_message(f"A contact with email '{email}' already exists in HubSpot.")
                elif "INVALID_EMAIL" in str(error_body):
                    yield self.create_text_message(f"The email address '{email}' is invalid.")
                else:
                    yield self.create_text_message(f"HubSpot API error: {str(e)}")
                return
                
        except Exception as e:
            yield self.create_text_message(f"Error creating contact: {str(e)}")
            return 