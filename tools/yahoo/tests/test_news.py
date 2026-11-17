from unittest.mock import Mock, patch

import pytest
from dify_plugin.entities.tool import ToolInvokeMessage
from yfinance import Ticker
from yfinance.data import YfData

from tools.news import YahooFinanceNewsTool


@pytest.mark.parametrize(
    ("metadata", "expected_url", "expected_provider"),
    [
        ({}, "", ""),
        ({"canonicalUrl": None, "provider": None}, "", ""),
        (
            {"canonicalUrl": "https://example.com/story", "provider": None},
            "https://example.com/story",
            "",
        ),
        ({"canonicalUrl": None, "provider": {"displayName": "Example"}}, "", "Example"),
        (
            {
                "canonicalUrl": "https://example.com/story",
                "provider": {"displayName": "Example"},
            },
            "https://example.com/story",
            "Example",
        ),
    ],
)
def test_news_handles_optional_graphql_metadata(
    metadata, expected_url, expected_provider
):
    asset = {
        "__typename": "Story",
        "id": "story-1",
        "title": "Example story",
        "contentAttributes": {
            "summary": "Example summary",
            "publishTime": "2026-11-16T12:00:00Z",
            **metadata,
        },
    }
    response = Mock(text="{}")
    response.json.return_value = {
        "data": {
            "lightyearList": {
                "main": {
                    "edges": [{"node": {"asset": asset}}],
                    "pageInfo": {"hasNextPage": False},
                }
            }
        },
    }
    with (
        patch.object(Ticker, "get_isin", return_value="US0378331005"),
        patch.object(YfData, "post", return_value=response),
    ):
        tool = YahooFinanceNewsTool.from_credentials({})
        messages = list(tool.invoke({"symbol": "AAPL"}))

    assert len(messages) == 1
    assert messages[0].type == ToolInvokeMessage.MessageType.JSON
    assert messages[0].message.json_object == {
        "news": [
            {
                "title": "Example story",
                "content": "Example summary",
                "url": expected_url,
                "provider": expected_provider,
                "publishDate": "2026-11-16T12:00:00Z",
            }
        ]
    }
