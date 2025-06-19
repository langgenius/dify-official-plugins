from collections.abc import Generator
from typing import Any, Dict, List
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from hubspot import HubSpot
from hubspot.crm.contacts.exceptions import ApiException


class GetCompaniesTool(Tool):
    """Tool for retrieving companies from HubSpot."""
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Retrieve companies from HubSpot.
        
        Args:
            tool_parameters: Dictionary of parameters
                - limit: Maximum number of companies to return (default: 10)
                
        Yields:
            ToolInvokeMessage: JSON or text message containing company data or error
        """
        try:
            # Extract parameters - convert string to int
            limit_str = tool_parameters.get("limit", "10")
            
            # Validate limit is a number
            try:
                limit = int(limit_str)
                # Cap the limit at 100
                limit = min(limit, 100)
                if limit < 1:
                    limit = 10  # Default to 10 if invalid
            except (ValueError, TypeError):
                # If conversion fails, use default
                yield self.create_text_message("Invalid limit format. Using default limit of 10.")
                limit = 10
            
            # Get access token from credentials
            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("HubSpot access token is required.")
                return
            
            # Create HubSpot client
            client = HubSpot(access_token=access_token)
            
            # Fetch companies from HubSpot
            api_response = client.crm.companies.basic_api.get_page(
                limit=limit,
                properties=["name", "domain", "website", "phone", "address", "city", 
                            "state", "country", "industry", "createdate", "hs_lastmodifieddate"]
            )
            
            # Process results
            companies = []
            for company in api_response.results:
                # Convert company to dict for easier manipulation
                company_dict = company.to_dict()
                
                # Extract the properties into a cleaner format
                company_data = {
                    "id": company_dict.get("id"),
                    "created_at": company_dict.get("properties", {}).get("createdate"),
                    "updated_at": company_dict.get("properties", {}).get("hs_lastmodifieddate"),
                    "name": company_dict.get("properties", {}).get("name"),
                    "domain": company_dict.get("properties", {}).get("domain"),
                    "website": company_dict.get("properties", {}).get("website"),
                    "phone": company_dict.get("properties", {}).get("phone"),
                    "address": company_dict.get("properties", {}).get("address"),
                    "city": company_dict.get("properties", {}).get("city"),
                    "state": company_dict.get("properties", {}).get("state"),
                    "country": company_dict.get("properties", {}).get("country"),
                    "industry": company_dict.get("properties", {}).get("industry")
                }
                companies.append(company_data)
            
            # Return the results
            if not companies:
                yield self.create_text_message("No companies found.")
                return
            
            # Create a summary message
            summary = f"Retrieved {len(companies)} companies from HubSpot."
            yield self.create_text_message(summary)
            
            # Return the full data as JSON
            response = {
                "companies": companies,
                "total": len(companies)
            }
            yield self.create_json_message(response)
            
        except ApiException as e:
            yield self.create_text_message(f"HubSpot API error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error retrieving companies: {str(e)}") 