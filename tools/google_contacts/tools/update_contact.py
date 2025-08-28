import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class UpdateContactTool(Tool):
    """
    Tool to update an existing contact in Google Contacts.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Update an existing contact in Google Contacts API.

        Args:
            tool_parameters: Dictionary containing tool parameters
        """
        try:
            # Extract required parameters
            resource_name = tool_parameters.get("resource_name", "").strip()
            if not resource_name:
                yield self.create_text_message(
                    "Resource name is required (e.g., 'people/123456789')"
                )
                return

            # Get access token
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message(
                    "Access token not found. Please authenticate first."
                )
                return

            # First, get the current contact to preserve existing data and get etag
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            # Get current contact
            get_response = requests.get(
                f"https://people.googleapis.com/v1/{resource_name}?personFields=names,phoneNumbers,emailAddresses,organizations,biographies,etag",
                headers=headers,
                timeout=30,
            )

            if get_response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to retrieve existing contact: {get_response.text}"
                )
                return

            current_contact = get_response.json()
            etag = current_contact.get("etag", "")

            # Extract update parameters
            given_name = tool_parameters.get("given_name", "").strip()
            family_name = tool_parameters.get("family_name", "").strip()
            middle_name = tool_parameters.get("middle_name", "").strip()
            phone_number = tool_parameters.get("phone_number", "").strip()
            email_address = tool_parameters.get("email_address", "").strip()
            organization = tool_parameters.get("organization", "").strip()
            job_title = tool_parameters.get("job_title", "").strip()
            notes = tool_parameters.get("notes", "").strip()

            # Build updated contact data - start with current data
            updated_contact = {"resourceName": resource_name, "etag": etag}

            # Update names if provided
            if given_name or family_name or middle_name:
                current_names = current_contact.get("names", [{}])
                primary_name = current_names[0] if current_names else {}

                updated_name = {
                    "givenName": (
                        given_name if given_name else primary_name.get("givenName", "")
                    ),
                    "familyName": (
                        family_name
                        if family_name
                        else primary_name.get("familyName", "")
                    ),
                    "middleName": (
                        middle_name
                        if middle_name
                        else primary_name.get("middleName", "")
                    ),
                }
                updated_contact["names"] = [updated_name]
            else:
                # Keep existing names
                updated_contact["names"] = current_contact.get("names", [])

            # Update phone number if provided
            if phone_number:
                updated_contact["phoneNumbers"] = [
                    {"value": phone_number, "type": "mobile"}
                ]
            else:
                # Keep existing phone numbers
                updated_contact["phoneNumbers"] = current_contact.get(
                    "phoneNumbers", []
                )

            # Update email address if provided
            if email_address:
                updated_contact["emailAddresses"] = [
                    {"value": email_address, "type": "home"}
                ]
            else:
                # Keep existing email addresses
                updated_contact["emailAddresses"] = current_contact.get(
                    "emailAddresses", []
                )

            # Update organization and job title if provided
            if organization or job_title:
                current_orgs = current_contact.get("organizations", [{}])
                primary_org = current_orgs[0] if current_orgs else {}

                updated_org = {
                    "name": (
                        organization if organization else primary_org.get("name", "")
                    ),
                    "title": job_title if job_title else primary_org.get("title", ""),
                    "type": "work",
                }
                updated_contact["organizations"] = [updated_org]
            else:
                # Keep existing organizations
                updated_contact["organizations"] = current_contact.get(
                    "organizations", []
                )

            # Update notes if provided
            if notes:
                updated_contact["biographies"] = [
                    {"value": notes, "contentType": "TEXT_PLAIN"}
                ]
            else:
                # Keep existing biographies
                updated_contact["biographies"] = current_contact.get("biographies", [])

            # Prepare request headers for update
            update_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            # Set updatePersonFields to specify which fields to update
            update_fields = []
            if given_name or family_name or middle_name:
                update_fields.append("names")
            if phone_number:
                update_fields.append("phoneNumbers")
            if email_address:
                update_fields.append("emailAddresses")
            if organization or job_title:
                update_fields.append("organizations")
            if notes:
                update_fields.append("biographies")

            if not update_fields:
                yield self.create_text_message(
                    "No fields to update. Please provide at least one field to update."
                )
                return

            # Log the operation
            yield self.create_log_message(
                label="Updating Contact",
                data={"resource_name": resource_name, "update_fields": update_fields},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
            )

            # Make API request to update contact
            params = {"updatePersonFields": ",".join(update_fields)}

            update_response = requests.patch(
                f"https://people.googleapis.com/v1/{resource_name}:updateContact",
                headers=update_headers,
                params=params,
                data=json.dumps(updated_contact),
                timeout=30,
            )

            if update_response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate your Google account."
                )
                return
            elif update_response.status_code == 403:
                yield self.create_text_message(
                    "Permission denied. Please ensure you have granted contacts write access."
                )
                return
            elif update_response.status_code == 404:
                yield self.create_text_message(
                    f"Contact not found. The resource name '{resource_name}' may be invalid."
                )
                return
            elif update_response.status_code != 200:
                yield self.create_text_message(
                    f"API request failed with status {update_response.status_code}: {update_response.text}"
                )
                return

            # Parse response
            updated_contact_response = update_response.json()

            # Extract updated contact information
            updated_info = self._extract_contact_info(updated_contact_response)

            # Create result
            result_data = {
                "success": True,
                "message": f"Contact updated successfully",
                "updated_fields": update_fields,
                "contact": updated_info,
            }

            # Return structured data
            yield self.create_json_message(result_data)

            # Create summary text
            display_name = updated_info.get("display_name", "Unknown")
            summary = f"Successfully updated contact '{display_name}'"
            summary += f". Updated fields: {', '.join(update_fields)}"

            yield self.create_text_message(summary)

            # Log success
            yield self.create_log_message(
                label="Contact Updated",
                data={
                    "resource_name": resource_name,
                    "display_name": display_name,
                    "updated_fields": update_fields,
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
