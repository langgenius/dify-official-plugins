import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class SpotifyGetArtistTool(Tool):
    """
    Tool for getting detailed information about a Spotify artist.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get detailed information about a Spotify artist.

        Args:
            tool_parameters: Dictionary containing artist parameters

        Yields:
            ToolInvokeMessage: Artist information and status messages
        """
        # Extract parameters
        artist_id = tool_parameters.get("artist_id", "").strip()
        include_albums = tool_parameters.get("include_albums", False)
        include_top_tracks = tool_parameters.get("include_top_tracks", True)
        market = tool_parameters.get("market", "US")

        # Validate required parameters
        if not artist_id:
            yield self.create_text_message("Artist ID is required")
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
            label="Get Spotify Artist",
            data={
                "artist_id": artist_id,
                "include_albums": include_albums,
                "include_top_tracks": include_top_tracks,
                "market": market,
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

        try:
            # Prepare API request
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # Make API request for artist info
            response = requests.get(
                f"https://api.spotify.com/v1/artists/{artist_id}",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate with Spotify."
                )
                return
            elif response.status_code == 404:
                yield self.create_text_message(
                    f"Artist with ID '{artist_id}' not found."
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

            artist_data = response.json()

            # Process and format artist information
            artist_info = {
                "id": artist_data["id"],
                "name": artist_data["name"],
                "genres": artist_data["genres"],
                "popularity": artist_data["popularity"],
                "followers": {"total": artist_data["followers"]["total"]},
                "external_urls": artist_data["external_urls"],
                "images": artist_data["images"],
            }

            # Get top tracks if requested
            if include_top_tracks:
                try:
                    top_tracks_response = requests.get(
                        f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks",
                        headers=headers,
                        params={"market": market},
                        timeout=30,
                    )
                    if top_tracks_response.status_code == 200:
                        top_tracks_data = top_tracks_response.json()
                        artist_info["top_tracks"] = [
                            {
                                "id": track["id"],
                                "name": track["name"],
                                "popularity": track["popularity"],
                                "duration_ms": track["duration_ms"],
                                "explicit": track["explicit"],
                                "preview_url": track.get("preview_url"),
                                "album": {
                                    "id": track["album"]["id"],
                                    "name": track["album"]["name"],
                                    "release_date": track["album"]["release_date"],
                                },
                                "external_urls": track["external_urls"],
                            }
                            for track in top_tracks_data["tracks"]
                        ]
                except:
                    # Top tracks are optional, continue without them
                    pass

            # Get albums if requested
            if include_albums:
                try:
                    albums_response = requests.get(
                        f"https://api.spotify.com/v1/artists/{artist_id}/albums",
                        headers=headers,
                        params={
                            "market": market,
                            "include_groups": "album,single,compilation",
                            "limit": 20,
                        },
                        timeout=30,
                    )
                    if albums_response.status_code == 200:
                        albums_data = albums_response.json()
                        artist_info["albums"] = {
                            "total": albums_data["total"],
                            "items": [
                                {
                                    "id": album["id"],
                                    "name": album["name"],
                                    "album_type": album["album_type"],
                                    "release_date": album["release_date"],
                                    "total_tracks": album["total_tracks"],
                                    "images": album["images"],
                                    "external_urls": album["external_urls"],
                                }
                                for album in albums_data["items"]
                            ],
                        }
                except:
                    # Albums are optional, continue without them
                    pass

            # Get related artists
            try:
                related_response = requests.get(
                    f"https://api.spotify.com/v1/artists/{artist_id}/related-artists",
                    headers=headers,
                    timeout=30,
                )
                if related_response.status_code == 200:
                    related_data = related_response.json()
                    artist_info["related_artists"] = [
                        {
                            "id": artist["id"],
                            "name": artist["name"],
                            "popularity": artist["popularity"],
                            "genres": artist["genres"],
                        }
                        for artist in related_data["artists"][:10]  # Limit to top 10
                    ]
            except:
                # Related artists are optional, continue without them
                pass

            # Return formatted artist information
            yield self.create_json_message(artist_info)

            # Create summary text
            summary = f"Artist: '{artist_info['name']}'"
            summary += f"\nFollowers: {artist_info['followers']['total']:,}"
            summary += f"\nPopularity: {artist_info['popularity']}/100"

            if artist_info["genres"]:
                summary += f"\nGenres: {', '.join(artist_info['genres'])}"

            if artist_info.get("top_tracks"):
                summary += f"\n\nTop Tracks:"
                for i, track in enumerate(artist_info["top_tracks"][:5], 1):
                    summary += (
                        f"\n {i}. {track['name']} (from {track['album']['name']})"
                    )

            if artist_info.get("albums"):
                summary += f"\n\nAlbums: {artist_info['albums']['total']} total"
                recent_albums = [album for album in artist_info["albums"]["items"][:3]]
                if recent_albums:
                    summary += f"\nRecent releases:"
                    for album in recent_albums:
                        summary += f"\n • {album['name']} ({album['release_date'][:4]}) - {album['album_type'].title()}"

            if artist_info.get("related_artists"):
                related_names = [
                    artist["name"] for artist in artist_info["related_artists"][:5]
                ]
                summary += f"\n\nRelated Artists: {', '.join(related_names)}"

            yield self.create_text_message(summary)

            # If there are artist images, show the main one
            if artist_info["images"]:
                main_image = artist_info["images"][0]  # Usually the largest image
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
