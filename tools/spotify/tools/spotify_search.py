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
        if not isinstance(limit, (int, float)) or not 1 <= limit <= 50 or limit != int(limit):
            yield self.create_text_message("The maximum result count must be an integer from 1 through 50.")
            return
        limit = int(limit)
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

            params = {"q": query, "type": search_type, "market": market}
            search_results = {}
            # Spotify limits Development Mode searches to 10 results per type per request.
            for offset in range(0, limit, 10):
                response = requests.get(
                    "https://api.spotify.com/v1/search",
                    headers=headers,
                    params={**params, "limit": min(10, limit - offset), "offset": offset},
                    timeout=30,
                )
                if response.status_code == 401:
                    yield self.create_text_message(
                        "Authentication failed. Please re-authenticate with Spotify."
                    )
                    return
                if response.status_code != 200:
                    error_data = (
                        response.json()
                        if response.headers.get("content-type", "").startswith("application/json")
                        else {}
                    )
                    error_message = error_data.get("error", {}).get(
                        "message", f"API request failed with status {response.status_code}"
                    )
                    yield self.create_text_message(f"Spotify API error: {error_message}")
                    return

                page = response.json()
                for category in ("tracks", "albums", "artists", "playlists"):
                    if result := page.get(category):
                        bucket = search_results.setdefault(category, {"items": [], "total": result["total"]})
                        bucket["items"].extend(item for item in result["items"] if item is not None)
                if not any(result and result.get("next") for result in page.values()):
                    break

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
                        "popularity": track.get("popularity"),
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
                        "images": album.get("images", []),
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
                        "genres": artist.get("genres", []),
                        "popularity": artist.get("popularity"),
                        "followers": (artist.get("followers") or {}).get("total"),
                        "external_urls": artist["external_urls"],
                        "images": artist.get("images", []),
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
                        "owner": (playlist.get("owner") or {}).get("display_name"),
                        "public": playlist.get("public"),
                        "tracks_total": (playlist.get("items") or playlist.get("tracks") or {}).get("total"),
                        "external_urls": playlist["external_urls"],
                        "images": playlist.get("images", []),
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
