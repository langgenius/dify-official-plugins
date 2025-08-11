import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class SpotifyGetAlbumTool(Tool):
    """
    Tool for getting detailed information about a Spotify album.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get detailed information about a Spotify album.

        Args:
            tool_parameters: Dictionary containing album parameters

        Yields:
            ToolInvokeMessage: Album information and status messages
        """
        # Extract parameters
        album_id = tool_parameters.get("album_id", "").strip()
        market = tool_parameters.get("market", "US")

        # Validate required parameters
        if not album_id:
            yield self.create_text_message("Album ID is required")
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
            label="Get Spotify Album",
            data={"album_id": album_id, "market": market},
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

        try:
            # Prepare API request
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            params = {"market": market}

            # Make API request
            response = requests.get(
                f"https://api.spotify.com/v1/albums/{album_id}",
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
                yield self.create_text_message(f"Album with ID '{album_id}' not found.")
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

            album_data = response.json()

            # Process and format album information
            album_info = {
                "id": album_data["id"],
                "name": album_data["name"],
                "album_type": album_data["album_type"],
                "total_tracks": album_data["total_tracks"],
                "release_date": album_data["release_date"],
                "release_date_precision": album_data["release_date_precision"],
                "popularity": album_data.get("popularity", 0),
                "genres": album_data.get("genres", []),
                "label": album_data.get("label", ""),
                "artists": [
                    {
                        "id": artist["id"],
                        "name": artist["name"],
                        "external_urls": artist["external_urls"],
                    }
                    for artist in album_data["artists"]
                ],
                "external_urls": album_data["external_urls"],
                "images": album_data["images"],
                "copyrights": album_data.get("copyrights", []),
                "tracks": {
                    "total": album_data["tracks"]["total"],
                    "items": [
                        {
                            "id": track["id"],
                            "name": track["name"],
                            "track_number": track["track_number"],
                            "disc_number": track["disc_number"],
                            "duration_ms": track["duration_ms"],
                            "explicit": track["explicit"],
                            "preview_url": track.get("preview_url"),
                            "artists": [
                                {"id": artist["id"], "name": artist["name"]}
                                for artist in track["artists"]
                            ],
                            "external_urls": track["external_urls"],
                        }
                        for track in album_data["tracks"]["items"]
                    ],
                },
            }

            # Return formatted album information
            yield self.create_json_message(album_info)

            # Create summary text
            artist_names = [artist["name"] for artist in album_info["artists"]]
            summary = f"Album: '{album_info['name']}' by {', '.join(artist_names)}"
            summary += f"\nType: {album_info['album_type'].title()}"
            summary += f"\nReleased: {album_info['release_date']}"
            summary += f"\nTracks: {album_info['total_tracks']}"
            if album_info["genres"]:
                summary += f"\nGenres: {', '.join(album_info['genres'])}"
            if album_info["label"]:
                summary += f"\nLabel: {album_info['label']}"

            yield self.create_text_message(summary)

            # If there are album images, show the main one
            if album_info["images"]:
                main_image = album_info["images"][0]  # Usually the largest image
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
