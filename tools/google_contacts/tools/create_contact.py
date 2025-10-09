import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class CreateContactTool(Tool):
    """
    Tool to create a new contact in Google Contacts.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a new contact in Google Contacts API.

        Args:
            tool_parameters: Dictionary containing tool parameters
        """
        try:
            # Extract required parameters
            given_name = tool_parameters.get("given_name", "").strip()
            family_name = tool_parameters.get("family_name", "").strip()

            # At least one name is required
            if not given_name and not family_name:
                yield self.create_text_message(
                    "Either given name or family name is required"
                )
                return

            # Extract optional parameters
            middle_name = tool_parameters.get("middle_name", "").strip()
            phone_number = tool_parameters.get("phone_number", "").strip()
            email_address = tool_parameters.get("email_address", "").strip()
            organization = tool_parameters.get("organization", "").strip()
            job_title = tool_parameters.get("job_title", "").strip()
            notes = tool_parameters.get("notes", "").strip()

            # Get access token
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message(
                    "Access token not found. Please authenticate first."
                )
                return

            # Build contact data
            contact_data = {
                "names": [
                    {
                        "givenName": given_name,
                        "familyName": family_name,
                        "middleName": middle_name,
                    }
                ]
            }

            # Add phone number if provided
            if phone_number:
                contact_data["phoneNumbers"] = [
                    {"value": phone_number, "type": "mobile"}
                ]

            # Add email address if provided
            if email_address:
                contact_data["emailAddresses"] = [
                    {"value": email_address, "type": "home"}
                ]

            # Add organization and job title if provided
            if organization or job_title:
                contact_data["organizations"] = [
                    {"name": organization, "title": job_title, "type": "work"}
                ]

            # Add notes if provided
            if notes:
                contact_data["biographies"] = [
                    {"value": notes, "contentType": "TEXT_PLAIN"}
                ]

            # Prepare request headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            # Log the operation
            display_name = f"{given_name} {family_name}".strip()
            yield self.create_log_message(
                label="Creating Contact",
                data={
                    "display_name": display_name,
                    "has_phone": bool(phone_number),
                    "has_email": bool(email_address),
                    "has_organization": bool(organization),
                },
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
            )

            # Make API request
            base_url = "https://people.googleapis.com/v1/people:createContact"
            response = requests.post(
                base_url, headers=headers, data=json.dumps(contact_data), timeout=30
            )

            if response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate your Google account."
                )
                return
            elif response.status_code == 403:
                yield self.create_text_message(
                    "Permission denied. Please ensure you have granted contacts write access."
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"API request failed with status {response.status_code}: {response.text}"
                )
                return

            # Parse response
            created_contact = response.json()

            # Extract created contact information
            created_info = self._extract_contact_info(created_contact)

            # Create result
            result_data = {
                "success": True,
                "message": f"Contact '{display_name}' created successfully",
                "contact": created_info,
            }

            # Return structured data
            yield self.create_json_message(result_data)

            # Create summary text
            summary = f"Successfully created contact '{display_name}'"
            if phone_number:
                summary += f" with phone {phone_number}"
            if email_address:
                summary += f" and email {email_address}"
            if organization:
                summary += f" at {organization}"
                if job_title:
                    summary += f" as {job_title}"

            yield self.create_text_message(summary)

            # Log success
            yield self.create_log_message(
                label="Contact Created",
                data={
                    "resource_name": created_info.get("resource_name", ""),
                    "display_name": display_name,
                },
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
            )

        except requests.RequestException as e:
            yield self.create_log_message(
                label="Network Error",
                data={"error": str(e)},
                status=InvokeMessage.LogMessage.LogStatus.ERROR,
            )
            yield self.create_text_message(f"Network error occurred: {str(e)}")

        except Exception as e:
            yield self.create_log_message(
                label="Unexpected Error",
                data={"error": str(e), "type": type(e).__name__},
                status=InvokeMessage.LogMessage.LogStatus.ERROR,
            )
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")

    def _extract_contact_info(self, contact: dict) -> dict:
        """
        Extract relevant contact information from the API response.

        Args:
            contact: Raw contact data from API

        Returns:
            Dictionary with processed contact information
        """
        contact_info = {
            "resource_name": contact.get("resourceName", ""),
            "etag": contact.get("etag", ""),
        }

        # Extract names
        names = contact.get("names", [])
        if names:
            primary_name = names[0]
            contact_info.update(
                {
                    "display_name": primary_name.get("displayName", ""),
                    "given_name": primary_name.get("givenName", ""),
                    "family_name": primary_name.get("familyName", ""),
                    "middle_name": primary_name.get("middleName", ""),
                }
            )
        else:
            contact_info.update(
                {
                    "display_name": "Unnamed Contact",
                    "given_name": "",
                    "family_name": "",
                    "middle_name": "",
                }
            )

        # Extract phone numbers
        phone_numbers = contact.get("phoneNumbers", [])
        contact_info["phone_numbers"] = [
            {
                "value": phone.get("value", ""),
                "type": phone.get("type", ""),
                "formatted_type": phone.get("formattedType", ""),
            }
            for phone in phone_numbers
        ]

        # Extract email addresses
        email_addresses = contact.get("emailAddresses", [])
        contact_info["email_addresses"] = [
            {
                "value": email.get("value", ""),
                "type": email.get("type", ""),
                "formatted_type": email.get("formattedType", ""),
            }
            for email in email_addresses
        ]

        # Extract organizations
        organizations = contact.get("organizations", [])
        if organizations:
            contact_info["organization"] = organizations[0].get("name", "")
            contact_info["job_title"] = organizations[0].get("title", "")
        else:
            contact_info["organization"] = ""
            contact_info["job_title"] = ""

        # Extract biography/notes
        biographies = contact.get("biographies", [])
        if biographies:
            contact_info["notes"] = biographies[0].get("value", "")
        else:
            contact_info["notes"] = ""

        return contact_info
