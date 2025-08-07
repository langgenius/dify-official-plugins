import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class SpotifySearchTool(Tool):
    """
    Tool for searching Spotify content including tracks, albums, artists, and playlists.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Search for content on Spotify.

        Args:
            tool_parameters: Dictionary containing search parameters

        Yields:
            ToolInvokeMessage: Search results and status messages
        """
        # Extract parameters
        query = tool_parameters.get("query", "").strip()
        search_type = tool_parameters.get("type", "track,album,artist")
        limit = tool_parameters.get("limit", 20)
        market = tool_parameters.get("market", "US")

        # Validate required parameters
        if not query:
            yield self.create_text_message("Search query is required")
            return

        # Get credentials
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message(
                "Spotify access token is required. Please authenticate first."
            )
            return

        # Log search operation
        yield self.create_log_message(
            label="Spotify Search",
            data={
                "query": query,
                "type": search_type,
                "limit": limit,
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

            params = {"q": query, "type": search_type, "limit": limit, "market": market}

            # Make API request
            response = requests.get(
                "https://api.spotify.com/v1/search",
                headers=headers,
                params=params,
                timeout=30,
            )

            if response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate with Spotify."
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

            search_results = response.json()

            # Process and format results
            formatted_results = {"query": query, "total_results": 0, "results": {}}

            # Process tracks
            if "tracks" in search_results and search_results["tracks"]["items"]:
                tracks = []
                for track in search_results["tracks"]["items"]:
                    track_info = {
                        "id": track["id"],
                        "name": track["name"],
                        "artists": [artist["name"] for artist in track["artists"]],
                        "album": track["album"]["name"],
                        "duration_ms": track["duration_ms"],
                        "popularity": track["popularity"],
                        "external_urls": track["external_urls"],
                        "preview_url": track.get("preview_url"),
                        "explicit": track["explicit"],
                    }
                    tracks.append(track_info)

                formatted_results["results"]["tracks"] = {
                    "total": search_results["tracks"]["total"],
                    "items": tracks,
                }
                formatted_results["total_results"] += len(tracks)

            # Process albums
            if "albums" in search_results and search_results["albums"]["items"]:
                albums = []
                for album in search_results["albums"]["items"]:
                    album_info = {
                        "id": album["id"],
                        "name": album["name"],
                        "artists": [artist["name"] for artist in album["artists"]],
                        "album_type": album["album_type"],
                        "total_tracks": album["total_tracks"],
                        "release_date": album["release_date"],
                        "external_urls": album["external_urls"],
                        "images": album["images"],
                    }
                    albums.append(album_info)

                formatted_results["results"]["albums"] = {
                    "total": search_results["albums"]["total"],
                    "items": albums,
                }
                formatted_results["total_results"] += len(albums)

            # Process artists
            if "artists" in search_results and search_results["artists"]["items"]:
                artists = []
                for artist in search_results["artists"]["items"]:
                    artist_info = {
                        "id": artist["id"],
                        "name": artist["name"],
                        "genres": artist["genres"],
                        "popularity": artist["popularity"],
                        "followers": artist["followers"]["total"],
                        "external_urls": artist["external_urls"],
                        "images": artist["images"],
                    }
                    artists.append(artist_info)

                formatted_results["results"]["artists"] = {
                    "total": search_results["artists"]["total"],
                    "items": artists,
                }
                formatted_results["total_results"] += len(artists)

            # Process playlists
            if "playlists" in search_results and search_results["playlists"]["items"]:
                playlists = []
                for playlist in search_results["playlists"]["items"]:
                    playlist_info = {
                        "id": playlist["id"],
                        "name": playlist["name"],
                        "description": playlist.get("description", ""),
                        "owner": playlist["owner"]["display_name"],
                        "public": playlist["public"],
                        "tracks_total": playlist["tracks"]["total"],
                        "external_urls": playlist["external_urls"],
                        "images": playlist["images"],
                    }
                    playlists.append(playlist_info)

                formatted_results["results"]["playlists"] = {
                    "total": search_results["playlists"]["total"],
                    "items": playlists,
                }
                formatted_results["total_results"] += len(playlists)

            # Return results
            yield self.create_json_message(formatted_results)

            # Create summary text
            summary_parts = []
            if "tracks" in formatted_results["results"]:
                summary_parts.append(
                    f"{len(formatted_results['results']['tracks']['items'])} tracks"
                )
            if "albums" in formatted_results["results"]:
                summary_parts.append(
                    f"{len(formatted_results['results']['albums']['items'])} albums"
                )
            if "artists" in formatted_results["results"]:
                summary_parts.append(
                    f"{len(formatted_results['results']['artists']['items'])} artists"
                )
            if "playlists" in formatted_results["results"]:
                summary_parts.append(
                    f"{len(formatted_results['results']['playlists']['items'])} playlists"
                )

            summary = f"Found {', '.join(summary_parts)} for '{query}'"
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
