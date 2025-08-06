import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class SpotifyControlPlaybackTool(Tool):
    """
    Tool for controlling Spotify playback (play, pause, skip, volume, etc.).
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Control Spotify playback on the user's devices.

        Args:
            tool_parameters: Dictionary containing playback control parameters

        Yields:
            ToolInvokeMessage: Control results and status messages
        """
        # Extract parameters
        action = tool_parameters.get("action", "").strip().lower()
        device_id = tool_parameters.get("device_id", "").strip()
        volume = tool_parameters.get("volume")
        track_uri = tool_parameters.get("track_uri", "").strip()
        position_ms = tool_parameters.get("position_ms")

        # Validate required parameters
        if not action:
            yield self.create_text_message("Action is required")
            return

        valid_actions = [
            "play",
            "pause",
            "next",
            "previous",
            "set_volume",
            "seek",
            "shuffle",
            "repeat",
            "transfer",
        ]
        if action not in valid_actions:
            yield self.create_text_message(
                f"Invalid action. Must be one of: {', '.join(valid_actions)}"
            )
            return

        # Get credentials
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message(
                "Spotify access token is required. Please authenticate first."
            )
            return

        # Log operation
        yield self.create_log_message(
            label="Spotify Playback Control",
            data={
                "action": action,
                "device_id": device_id or "default",
                "volume": volume,
                "track_uri": track_uri,
                "position_ms": position_ms,
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

        try:
            # Prepare API request headers
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # Prepare device parameter for requests
            device_params = {}
            if device_id:
                device_params["device_id"] = device_id

            # Execute the requested action
            if action == "play":
                # Play music
                url = "https://api.spotify.com/v1/me/player/play"
                body = {}

                if track_uri:
                    if track_uri.startswith("spotify:"):
                        body["uris"] = [track_uri]
                    else:
                        # Assume it's a context URI (playlist, album, etc.)
                        body["context_uri"] = track_uri

                if position_ms is not None:
                    body["position_ms"] = position_ms

                response = requests.put(
                    url, headers=headers, params=device_params, json=body, timeout=30
                )
                action_text = "Started playback"
                if track_uri:
                    action_text += f" for {track_uri}"

            elif action == "pause":
                # Pause playback
                url = "https://api.spotify.com/v1/me/player/pause"
                response = requests.put(
                    url, headers=headers, params=device_params, timeout=30
                )
                action_text = "Paused playback"

            elif action == "next":
                # Skip to next track
                url = "https://api.spotify.com/v1/me/player/next"
                response = requests.post(
                    url, headers=headers, params=device_params, timeout=30
                )
                action_text = "Skipped to next track"

            elif action == "previous":
                # Skip to previous track
                url = "https://api.spotify.com/v1/me/player/previous"
                response = requests.post(
                    url, headers=headers, params=device_params, timeout=30
                )
                action_text = "Skipped to previous track"

            elif action == "set_volume":
                # Set volume
                if volume is None or not (0 <= volume <= 100):
                    yield self.create_text_message("Volume must be between 0 and 100")
                    return

                url = "https://api.spotify.com/v1/me/player/volume"
                params = {**device_params, "volume_percent": volume}
                response = requests.put(url, headers=headers, params=params, timeout=30)
                action_text = f"Set volume to {volume}%"

            elif action == "seek":
                # Seek to position
                if position_ms is None or position_ms < 0:
                    yield self.create_text_message(
                        "Position in milliseconds is required for seek action"
                    )
                    return

                url = "https://api.spotify.com/v1/me/player/seek"
                params = {**device_params, "position_ms": position_ms}
                response = requests.put(url, headers=headers, params=params, timeout=30)
                action_text = f"Seeked to position {position_ms}ms"

            elif action == "shuffle":
                # Toggle shuffle
                shuffle_state = tool_parameters.get("shuffle", True)
                url = "https://api.spotify.com/v1/me/player/shuffle"
                params = {
                    **device_params,
                    "state": "true" if shuffle_state else "false",
                }
                response = requests.put(url, headers=headers, params=params, timeout=30)
                action_text = f"Shuffle {'enabled' if shuffle_state else 'disabled'}"

            elif action == "repeat":
                # Set repeat mode
                repeat_state = tool_parameters.get(
                    "repeat_state", "context"
                )  # track, context, off
                if repeat_state not in ["track", "context", "off"]:
                    yield self.create_text_message(
                        "Repeat state must be 'track', 'context', or 'off'"
                    )
                    return

                url = "https://api.spotify.com/v1/me/player/repeat"
                params = {**device_params, "state": repeat_state}
                response = requests.put(url, headers=headers, params=params, timeout=30)
                action_text = f"Repeat set to {repeat_state}"

            elif action == "transfer":
                # Transfer playback to device
                if not device_id:
                    yield self.create_text_message(
                        "Device ID is required for transfer action"
                    )
                    return

                url = "https://api.spotify.com/v1/me/player"
                body = {
                    "device_ids": [device_id],
                    "play": tool_parameters.get("start_playing", False),
                }
                response = requests.put(url, headers=headers, json=body, timeout=30)
                action_text = f"Transferred playback to device {device_id}"

            # Handle response
            if response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate with Spotify."
                )
                return
            elif response.status_code == 403:
                yield self.create_text_message(
                    "Access forbidden. Make sure your Spotify account has premium features."
                )
                return
            elif response.status_code == 404:
                if action == "transfer":
                    yield self.create_text_message(
                        f"Device with ID '{device_id}' not found or not available."
                    )
                else:
                    yield self.create_text_message(
                        "No active device found. Please start Spotify on a device first or specify a device ID."
                    )
                return
            elif response.status_code not in [200, 204]:
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

            # Get current playback state to show result
            try:
                state_response = requests.get(
                    "https://api.spotify.com/v1/me/player", headers=headers, timeout=30
                )

                current_state = {}
                if state_response.status_code == 200:
                    playback_data = state_response.json()
                    if playback_data:
                        current_state = {
                            "is_playing": playback_data.get("is_playing", False),
                            "device": {
                                "name": playback_data["device"]["name"],
                                "type": playback_data["device"]["type"],
                                "volume_percent": playback_data["device"][
                                    "volume_percent"
                                ],
                            },
                            "shuffle_state": playback_data.get("shuffle_state", False),
                            "repeat_state": playback_data.get("repeat_state", "off"),
                            "progress_ms": playback_data.get("progress_ms", 0),
                        }

                        if playback_data.get("item"):
                            current_state["track"] = {
                                "id": playback_data["item"]["id"],
                                "name": playback_data["item"]["name"],
                                "artists": [
                                    artist["name"]
                                    for artist in playback_data["item"]["artists"]
                                ],
                                "duration_ms": playback_data["item"]["duration_ms"],
                            }
            except:
                # Current state is optional
                pass

            # Return result
            result = {
                "action": action,
                "success": True,
                "message": action_text,
                "current_state": current_state,
            }

            yield self.create_json_message(result)
            yield self.create_text_message(f"✅ {action_text}")

            # Show current track if playing
            if current_state.get("track") and current_state.get("is_playing"):
                track = current_state["track"]
                progress_min = current_state["progress_ms"] // 60000
                progress_sec = (current_state["progress_ms"] % 60000) // 1000
                duration_min = track["duration_ms"] // 60000
                duration_sec = (track["duration_ms"] % 60000) // 1000

                track_info = (
                    f"🎵 Now playing: {track['name']} by {', '.join(track['artists'])}"
                )
                track_info += f"\n⏱️ Progress: {progress_min}:{progress_sec:02d} / {duration_min}:{duration_sec:02d}"
                track_info += f"\n🔊 Device: {current_state['device']['name']} (Volume: {current_state['device']['volume_percent']}%)"

                yield self.create_text_message(track_info)

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
