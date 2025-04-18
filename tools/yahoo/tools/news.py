from collections.abc import Generator
from typing import Any
import yfinance
from requests.exceptions import HTTPError, ReadTimeout
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

class YahooFinanceNewsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        query = tool_parameters.get("symbol", "")
        if not query:
            yield self.create_text_message("Please input symbol")
            return
        try:
            yield from self.run(ticker=query)
        except (HTTPError, ReadTimeout):
            yield self.create_text_message("There is a internet connection problem. Please try again later.")

    def run(self, ticker: str) -> Generator[ToolInvokeMessage, None, None]:
        company = yfinance.Ticker(ticker)
        try:
            if company.isin is None:
                yield self.create_text_message(f"Company ticker {ticker} not found.")
        except (HTTPError, ReadTimeout, ConnectionError):
            yield self.create_text_message(f"Company ticker {ticker} not found.")
        
        news_items = []
        try:
            # Extract news items that are STORY type
            raw_news = company.news
            for item in raw_news:
                content = item.get('content', {})
                if content.get('contentType') == 'STORY':
                    # Get content from either description or summary
                    article_content = content.get('description', '')
                    if not article_content:
                        article_content = content.get('summary', '')
                    
                    news_items.append({
                        'title': content.get('title', ''),
                        'content': article_content,
                        'url': content.get('canonicalUrl', {}).get('url', ''),
                        'provider': content.get('provider', {}).get('displayName', ''),
                        'publishDate': content.get('pubDate', '')
                    })
            
        except (HTTPError, ReadTimeout, ConnectionError):
            if not news_items:
                yield self.create_text_message(f"There is nothing about {ticker} ticker")
                return
        
        if not news_items:
            yield self.create_text_message(f"No news found for company that searched with {ticker} ticker.")
            return
        
        yield self.create_json_message({"news": news_items})
