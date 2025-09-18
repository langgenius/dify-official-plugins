import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class SpotifyGetTrackTool(Tool):
    """
    Tool for getting detailed information about a Spotify track.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get detailed information about a Spotify track.

        Args:
            tool_parameters: Dictionary containing track parameters

        Yields:
            ToolInvokeMessage: Track information and status messages
        """
        # Extract parameters
        track_id = tool_parameters.get("track_id", "").strip()
        market = tool_parameters.get("market", "US")

        # Validate required parameters
        if not track_id:
            yield self.create_text_message("Track ID is required")
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
            label="Get Spotify Track",
            data={"track_id": track_id, "market": market},
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

        try:
            # Prepare API request
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            params = {"market": market}

            # Make API request for track info
            response = requests.get(
                f"https://api.spotify.com/v1/tracks/{track_id}",
                headers=headers,
                params=params,
                timeout=30,
            )

            if response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate with Spotify."
                )
                return
            elif response.status_code == 404:
                yield self.create_text_message(f"Track with ID '{track_id}' not found.")
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

            track_data = response.json()

            # Get audio features for additional information
            audio_features = None
            try:
                features_response = requests.get(
                    f"https://api.spotify.com/v1/audio-features/{track_id}",
                    headers=headers,
                    timeout=30,
                )
                if features_response.status_code == 200:
                    audio_features = features_response.json()
            except:
                # Audio features are optional, continue without them
                pass

            # Process and format track information
            track_info = {
                "id": track_data["id"],
                "name": track_data["name"],
                "duration_ms": track_data["duration_ms"],
                "explicit": track_data["explicit"],
                "popularity": track_data["popularity"],
                "preview_url": track_data.get("preview_url"),
                "track_number": track_data.get("track_number"),
                "disc_number": track_data.get("disc_number", 1),
                "is_local": track_data.get("is_local", False),
                "artists": [
                    {
                        "id": artist["id"],
                        "name": artist["name"],
                        "external_urls": artist["external_urls"],
                    }
                    for artist in track_data["artists"]
                ],
                "album": {
                    "id": track_data["album"]["id"],
                    "name": track_data["album"]["name"],
                    "album_type": track_data["album"]["album_type"],
                    "release_date": track_data["album"]["release_date"],
                    "total_tracks": track_data["album"]["total_tracks"],
                    "images": track_data["album"]["images"],
                    "external_urls": track_data["album"]["external_urls"],
                },
                "external_urls": track_data["external_urls"],
                "external_ids": track_data.get("external_ids", {}),
                "available_markets": track_data.get("available_markets", []),
            }

            # Add audio features if available
            if audio_features:
                track_info["audio_features"] = {
                    "danceability": audio_features.get("danceability"),
                    "energy": audio_features.get("energy"),
                    "key": audio_features.get("key"),
                    "loudness": audio_features.get("loudness"),
                    "mode": audio_features.get("mode"),
                    "speechiness": audio_features.get("speechiness"),
                    "acousticness": audio_features.get("acousticness"),
                    "instrumentalness": audio_features.get("instrumentalness"),
                    "liveness": audio_features.get("liveness"),
                    "valence": audio_features.get("valence"),
                    "tempo": audio_features.get("tempo"),
                    "time_signature": audio_features.get("time_signature"),
                }

            # Return formatted track information
            yield self.create_json_message(track_info)

            # Create summary text
            artist_names = [artist["name"] for artist in track_info["artists"]]
            duration_min = track_info["duration_ms"] // 60000
            duration_sec = (track_info["duration_ms"] % 60000) // 1000

            summary = f"Track: '{track_info['name']}' by {', '.join(artist_names)}"
            summary += f"\nAlbum: {track_info['album']['name']}"
            summary += f"\nDuration: {duration_min}:{duration_sec:02d}"
            summary += f"\nPopularity: {track_info['popularity']}/100"
            summary += f"\nReleased: {track_info['album']['release_date']}"

            if track_info.get("audio_features"):
                af = track_info["audio_features"]
                summary += f"\n\nAudio Features:"
                summary += f"\n• Danceability: {af['danceability']:.2f}"
                summary += f"\n• Energy: {af['energy']:.2f}"
                summary += f"\n• Valence (Positivity): {af['valence']:.2f}"
                summary += f"\n• Tempo: {af['tempo']:.0f} BPM"

            yield self.create_text_message(summary)

            # If there's a preview URL, provide it
            if track_info["preview_url"]:
                yield self.create_link_message(track_info["preview_url"])

            # If there are album images, show the main one
            if track_info["album"]["images"]:
                main_image = track_info["album"]["images"][
                    0
                ]  # Usually the largest image
                yield self.create_image_message(main_image["url"])

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
