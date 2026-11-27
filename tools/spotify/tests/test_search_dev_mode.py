from unittest.mock import Mock, patch

from dify_plugin.entities.tool import ToolInvokeMessage
from tools.spotify_search import SpotifySearchTool


def test_search_paginates_and_accepts_development_mode_payload():
    def mock_search(url, *, params, **kwargs):
        assert url == "https://api.spotify.com/v1/search"
        assert params["limit"] <= 10
        offset = params["offset"]
        last = offset + params["limit"]
        artists = [
            {"id": str(i), "name": f"Artist {i}", "images": [], "external_urls": {}}
            for i in range(offset, last)
        ]
        playlists = [
            {
                "id": str(i),
                "name": f"Playlist {i}",
                "public": True,
                "owner": {},
                "items": {"total": 4},
                "external_urls": {},
            }
            for i in range(offset, last)
        ]
        next_page = "https://api.spotify.com/v1/search" if last < 30 else None
        return Mock(
            status_code=200,
            json=lambda: {
                "artists": {"items": artists, "total": 30, "next": next_page},
                "playlists": {"items": playlists, "total": 30, "next": next_page},
            },
        )

    tool = SpotifySearchTool.from_credentials({"access_token": "test-token"})
    with patch("requests.get", side_effect=mock_search) as get:
        messages = list(
            tool.invoke({"query": "Dify", "type": "artist,playlist", "limit": 23})
        )

    assert [
        (c.kwargs["params"]["offset"], c.kwargs["params"]["limit"])
        for c in get.call_args_list
    ] == [
        (0, 10),
        (10, 10),
        (20, 3),
    ]
    (result,) = [
        m.message.json_object
        for m in messages
        if m.type == ToolInvokeMessage.MessageType.JSON
    ]
    assert result["total_results"] == 46
    assert len(result["results"]["artists"]["items"]) == 23
    assert result["results"]["artists"]["items"][0]["followers"] is None
    assert result["results"]["playlists"]["items"][0]["tracks_total"] == 4
