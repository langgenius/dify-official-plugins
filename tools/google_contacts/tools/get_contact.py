from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class GetContactTool(Tool):
    """
    Tool to get detailed information about a specific contact.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get detailed contact information from Google Contacts API.

        Args:
            tool_parameters: Dictionary containing tool parameters
        """
        try:
            # Extract parameters
            resource_name = tool_parameters.get("resource_name", "").strip()
            person_fields = tool_parameters.get(
                "person_fields",
                "names,phoneNumbers,emailAddresses,organizations,addresses,biographies,birthdays,urls,relations",
            )

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

            # Prepare request headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            # Build API URL
            base_url = f"https://people.googleapis.com/v1/{resource_name}"
            params = {"personFields": person_fields}

            # Log the operation
            yield self.create_log_message(
                label="Getting Contact Details",
                data={"resource_name": resource_name, "person_fields": person_fields},
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
            elif response.status_code == 404:
                yield self.create_text_message(
                    f"Contact not found. The resource name '{resource_name}' may be invalid."
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"API request failed with status {response.status_code}: {response.text}"
                )
                return

            # Parse response
            contact_data = response.json()

            # Process contact information
            contact_info = self._extract_detailed_contact_info(contact_data)

            # Return structured data
            yield self.create_json_message(contact_info)

            # Create summary text
            display_name = contact_info.get("display_name", "Unknown")
            summary = f"Retrieved contact details for '{display_name}'"

            details = []
            if contact_info.get("phone_numbers"):
                details.append(f"{len(contact_info['phone_numbers'])} phone number(s)")
            if contact_info.get("email_addresses"):
                details.append(
                    f"{len(contact_info['email_addresses'])} email address(es)"
                )
            if contact_info.get("organization"):
                details.append(f"works at {contact_info['organization']}")
            if contact_info.get("addresses"):
                details.append(f"{len(contact_info['addresses'])} address(es)")

            if details:
                summary += f" - {', '.join(details)}"

            yield self.create_text_message(summary)

            # Log success
            yield self.create_log_message(
                label="Contact Retrieved",
                data={
                    "resource_name": resource_name,
                    "display_name": display_name,
                    "has_phone": bool(contact_info.get("phone_numbers")),
                    "has_email": bool(contact_info.get("email_addresses")),
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

    def _extract_detailed_contact_info(self, contact: dict) -> dict:
        """
        Extract detailed contact information from the API response.

        Args:
            contact: Raw contact data from API

        Returns:
            Dictionary with detailed contact information
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
                    "honorific_prefix": primary_name.get("honorificPrefix", ""),
                    "honorific_suffix": primary_name.get("honorificSuffix", ""),
                    "phonetic_given_name": primary_name.get("phoneticGivenName", ""),
                    "phonetic_family_name": primary_name.get("phoneticFamilyName", ""),
                }
            )
        else:
            contact_info.update(
                {
                    "display_name": "Unnamed Contact",
                    "given_name": "",
                    "family_name": "",
                    "middle_name": "",
                    "honorific_prefix": "",
                    "honorific_suffix": "",
                    "phonetic_given_name": "",
                    "phonetic_family_name": "",
                }
            )

        # Extract phone numbers
        phone_numbers = contact.get("phoneNumbers", [])
        contact_info["phone_numbers"] = [
            {
                "value": phone.get("value", ""),
                "canonical_form": phone.get("canonicalForm", ""),
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
                "display_name": email.get("displayName", ""),
            }
            for email in email_addresses
        ]

        # Extract organizations
        organizations = contact.get("organizations", [])
        contact_info["organizations"] = [
            {
                "name": org.get("name", ""),
                "title": org.get("title", ""),
                "type": org.get("type", ""),
                "formatted_type": org.get("formattedType", ""),
                "department": org.get("department", ""),
                "domain": org.get("domain", ""),
                "start_date": org.get("startDate", {}),
                "end_date": org.get("endDate", {}),
                "current": org.get("current", True),
            }
            for org in organizations
        ]

        # Set primary organization info for backward compatibility
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
                "formatted_type": address.get("formattedType", ""),
                "street_address": address.get("streetAddress", ""),
                "city": address.get("city", ""),
                "region": address.get("region", ""),
                "postal_code": address.get("postalCode", ""),
                "country": address.get("country", ""),
                "country_code": address.get("countryCode", ""),
                "extended_address": address.get("extendedAddress", ""),
                "po_box": address.get("poBox", ""),
            }
            for address in addresses
        ]

        # Extract biographies/notes
        biographies = contact.get("biographies", [])
        if biographies:
            contact_info["biography"] = biographies[0].get("value", "")
            contact_info["biography_content_type"] = biographies[0].get(
                "contentType", ""
            )
        else:
            contact_info["biography"] = ""
            contact_info["biography_content_type"] = ""

        # Extract birthdays
        birthdays = contact.get("birthdays", [])
        if birthdays:
            birthday = birthdays[0].get("date", {})
            contact_info["birthday"] = {
                "year": birthday.get("year", 0),
                "month": birthday.get("month", 0),
                "day": birthday.get("day", 0),
            }
        else:
            contact_info["birthday"] = {}

        # Extract URLs
        urls = contact.get("urls", [])
        contact_info["urls"] = [
            {
                "value": url.get("value", ""),
                "type": url.get("type", ""),
                "formatted_type": url.get("formattedType", ""),
            }
            for url in urls
        ]

        # Extract relations
        relations = contact.get("relations", [])
        contact_info["relations"] = [
            {
                "person": relation.get("person", ""),
                "type": relation.get("type", ""),
                "formatted_type": relation.get("formattedType", ""),
            }
            for relation in relations
        ]

        return contact_info
