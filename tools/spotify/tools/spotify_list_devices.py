import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class SpotifyListDevicesTool(Tool):
    """
    Tool for listing available Spotify playback devices.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List all available Spotify playback devices for the authenticated user.

        Args:
            tool_parameters: Dictionary containing device parameters (none required)

        Yields:
            ToolInvokeMessage: Device list and status messages
        """
        # Get credentials
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message(
                "Spotify access token is required. Please authenticate first."
            )
            return

        # Log operation
        yield self.create_log_message(
            label="List Spotify Devices",
            data={"action": "get_available_devices"},
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

        try:
            # Prepare API request
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # Make API request to get available devices
            response = requests.get(
                "https://api.spotify.com/v1/me/player/devices",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate with Spotify."
                )
                return
            elif response.status_code == 403:
                yield self.create_text_message(
                    "Access forbidden. Make sure your Spotify account has premium features or the required permissions."
                )
                return
            elif response.status_code != 200:
                error_data = (
                    response.json()
                    if response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
                error_message = error_data.get("error", {}).get(
                    "message", f"API request failed with status {response.status_code}"
                )
                yield self.create_text_message(f"Spotify API error: {error_message}")
                return

            devices_data = response.json()
            devices = devices_data.get("devices", [])

            if not devices:
                yield self.create_text_message(
                    "No Spotify devices found. Make sure you have Spotify open on at least one device."
                )
                return

            # Process and format device information
            devices_info = {"total_devices": len(devices), "devices": []}

            active_device = None

            for device in devices:
                device_info = {
                    "id": device["id"],
                    "name": device["name"],
                    "type": device["type"],
                    "is_active": device["is_active"],
                    "is_private_session": device["is_private_session"],
                    "is_restricted": device["is_restricted"],
                    "volume_percent": device["volume_percent"],
                    "supports_volume": device.get("supports_volume", False),
                }

                devices_info["devices"].append(device_info)

                if device["is_active"]:
                    active_device = device_info

            # Add active device info to the top level
            if active_device:
                devices_info["active_device"] = active_device

            # Return formatted device information
            yield self.create_json_message(devices_info)

            # Create summary text
            summary = f"Found {len(devices)} Spotify device(s):\n"

            for i, device in enumerate(devices_info["devices"], 1):
                status = "🟢 Active" if device["is_active"] else "⚪ Available"
                device_type = device["type"].replace("_", " ").title()
                volume_info = (
                    f" (Volume: {device['volume_percent']}%)"
                    if device.get("volume_percent") is not None
                    else ""
                )

                summary += (
                    f"\n{i}. {device['name']} - {device_type} {status}{volume_info}"
                )

                if device["is_private_session"]:
                    summary += " [Private Session]"
                if device["is_restricted"]:
                    summary += " [Restricted]"

            if active_device:
                summary += f"\n\n🎵 Currently active: {active_device['name']} ({active_device['type'].replace('_', ' ').title()})"
            else:
                summary += "\n\n⏸️ No device currently active"

            yield self.create_text_message(summary)

        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timed out. Please try again.")
        except requests.exceptions.RequestException as e:
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
