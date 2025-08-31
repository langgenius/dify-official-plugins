from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class ListContactsTool(Tool):
    """
    Tool to list Google Contacts with pagination and filtering options.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List contacts from Google Contacts API.

        Args:
            tool_parameters: Dictionary containing tool parameters
        """
        try:
            # Extract parameters
            page_size = tool_parameters.get("page_size", 25)
            page_token = tool_parameters.get("page_token", "")
            person_fields = tool_parameters.get(
                "person_fields", "names,phoneNumbers,emailAddresses"
            )

            # Validate page_size
            if page_size < 1 or page_size > 2000:
                yield self.create_text_message("Page size must be between 1 and 2000")
                return

            # Get access token
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message(
                    "Access token not found. Please authenticate first."
                )
                return

            # Prepare request headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            # Build API URL
            base_url = "https://people.googleapis.com/v1/people/me/connections"
            params = {
                "pageSize": page_size,
                "personFields": person_fields,
            }

            if page_token:
                params["pageToken"] = page_token

            # Log the operation
            yield self.create_log_message(
                label="Listing Contacts",
                data={
                    "page_size": page_size,
                    "person_fields": person_fields,
                    "has_page_token": bool(page_token),
                },
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
            )

            # Make API request
            response = requests.get(
                base_url, headers=headers, params=params, timeout=30
            )

            if response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate your Google account."
                )
                return
            elif response.status_code == 403:
                yield self.create_text_message(
                    "Permission denied. Please ensure you have granted contacts access."
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"API request failed with status {response.status_code}: {response.text}"
                )
                return

            # Parse response
            data = response.json()
            connections = data.get("connections", [])
            next_page_token = data.get("nextPageToken", "")
            total_people = data.get("totalPeople", 0)

            # Process contacts
            processed_contacts = []
            for contact in connections:
                contact_info = self._extract_contact_info(contact)
                processed_contacts.append(contact_info)

            # Create result
            result = {
                "contacts": processed_contacts,
                "total_contacts": len(processed_contacts),
                "next_page_token": next_page_token,
                "total_people": total_people,
                "has_more_pages": bool(next_page_token),
            }

            # Return structured data
            yield self.create_json_message(result)

            # Create summary text
            summary = f"Retrieved {len(processed_contacts)} contacts"
            if next_page_token:
                summary += f" (more pages available)"
            summary += f". Total people in account: {total_people}"

            yield self.create_text_message(summary)

            # Log success
            yield self.create_log_message(
                label="Contacts Retrieved",
                data={
                    "contacts_count": len(processed_contacts),
                    "has_next_page": bool(next_page_token),
                    "total_people": total_people,
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

        # Extract addresses
        addresses = contact.get("addresses", [])
        contact_info["addresses"] = [
            {
                "formatted_value": address.get("formattedValue", ""),
                "type": address.get("type", ""),
                "street_address": address.get("streetAddress", ""),
                "city": address.get("city", ""),
                "region": address.get("region", ""),
                "postal_code": address.get("postalCode", ""),
                "country": address.get("country", ""),
            }
            for address in addresses
        ]

        return contact_info
