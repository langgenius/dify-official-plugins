import time
from collections.abc import Generator, Mapping
from typing import Any

import requests
from dify_plugin.entities.datasource import (
    WebSiteInfo,
    WebSiteInfoDetail,
    WebsiteCrawlMessage,
)
from dify_plugin.interfaces.datasource.website import WebsiteCrawlDatasource

TAVILY_API_URL = "https://api.tavily.com"


class TavilySearchExtractDatasource(WebsiteCrawlDatasource):
    def _get_website_crawl(
        self, datasource_parameters: Mapping[str, Any]
    ) -> Generator[WebsiteCrawlMessage, None, None]:
        """
        Search the web using Tavily API and extract content from found pages.
        """
        # Get API key from credentials
        api_key = self.runtime.credentials.get("tavily_api_key")
        if not api_key:
            raise ValueError("Tavily API key not found in credentials")
        
        # Get search parameters
        query = datasource_parameters.get("query", "").strip()
        if not query:
            raise ValueError("Search query is required")
        
        search_depth = datasource_parameters.get("search_depth", "basic")
        topic = datasource_parameters.get("topic", "general")
        max_results = int(datasource_parameters.get("max_results", 5))
        include_domains = datasource_parameters.get("include_domains", "")
        exclude_domains = datasource_parameters.get("exclude_domains", "")
        include_images = datasource_parameters.get("include_images", False)
        include_answer = datasource_parameters.get("include_answer", True)
        include_raw_content = datasource_parameters.get("include_raw_content", True)
        
        try:
            # Initialize crawl result
            crawl_res = WebSiteInfo(web_info_list=[], status="", total=0, completed=0)
            
            # Start processing
            crawl_res.status = "processing"
            yield self.create_crawl_message(crawl_res)
            
            # Perform search using Tavily API
            search_results = self._perform_search(
                api_key=api_key,
                query=query,
                search_depth=search_depth,
                topic=topic,
                max_results=max_results,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                include_images=include_images,
                include_answer=include_answer,
                include_raw_content=include_raw_content
            )
            
            if not search_results.get("results"):
                crawl_res.status = "completed"
                crawl_res.total = 0
                crawl_res.completed = 0
                yield self.create_crawl_message(crawl_res)
                return
            
            # Process search results
            web_info_list = []
            total_results = len(search_results["results"])
            crawl_res.total = total_results
            
            for idx, result in enumerate(search_results["results"]):
                try:
                    # Create web info detail for each result
                    description = ""
                    if "published_date" in result:
                        description = f"Published: {result['published_date']}"
                    if "score" in result:
                        if description:
                            description += f" | Relevance: {result['score']}"
                        else:
                            description = f"Relevance: {result['score']}"
                    
                    content = result.get("content", "")
                    
                    # If raw content extraction is enabled and we don't have content, try to extract
                    if include_raw_content and not content:
                        try:
                            extracted_content = self._extract_content(api_key, [result.get("url", "")])
                            if extracted_content and extracted_content.get("results"):
                                content = extracted_content["results"][0].get("raw_content", "")
                        except Exception as e:
                            raise ValueError(f"Failed to extract content from {result.get('url', '')}: {str(e)}")
                    
                    web_info_detail = WebSiteInfoDetail(
                        source_url=result.get("url", ""),
                        title=result.get("title", ""),
                        description=description,
                        content=content
                    )
                    
                    web_info_list.append(web_info_detail)
                    
                    # Update progress
                    crawl_res.completed = idx + 1
                    crawl_res.web_info_list = web_info_list
                    yield self.create_crawl_message(crawl_res)
                    
                except Exception:
                    continue
            
            # Add AI answer as a summary if available
            if search_results.get("answer"):
                summary_content = f"AI Answer: {search_results['answer']}\n\n"
                summary_content += f"Found {len(web_info_list)} relevant results for query: {query}"
                
                summary_detail = WebSiteInfoDetail(
                    source_url="",
                    title="Search Summary",
                    description=f"Tavily search results for: {query}",
                    content=summary_content
                )
                web_info_list.insert(0, summary_detail)
            
            # Final result
            crawl_res.status = "completed"
            crawl_res.web_info_list = web_info_list
            crawl_res.total = len(web_info_list)
            crawl_res.completed = len(web_info_list)
            yield self.create_crawl_message(crawl_res)
            
        except Exception as e:
            raise ValueError(f"An error occurred: {str(e)}")
    
    def _perform_search(self, api_key: str, query: str, **kwargs) -> dict:
        """
        Perform search using Tavily Search API.
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Prepare search parameters
        search_params = {
            "query": query,
            "search_depth": kwargs.get("search_depth", "basic"),
            "topic": kwargs.get("topic", "general"),
            "max_results": kwargs.get("max_results", 5),
            "include_images": kwargs.get("include_images", False),
            "include_answer": kwargs.get("include_answer", True),
            "include_raw_content": kwargs.get("include_raw_content", True)
        }
        
        # Add domain filters if provided
        include_domains = kwargs.get("include_domains", "").strip()
        if include_domains:
            search_params["include_domains"] = [
                domain.strip() for domain in include_domains.replace(",", " ").split()
            ]
        
        exclude_domains = kwargs.get("exclude_domains", "").strip()
        if exclude_domains:
            search_params["exclude_domains"] = [
                domain.strip() for domain in exclude_domains.replace(",", " ").split()
            ]
        
        # For news topic, add days parameter
        if search_params.get("topic") == "news":
            search_params["days"] = 7  # Last 7 days of news
        
        response = requests.post(
            f"{TAVILY_API_URL}/search",
            json=search_params,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def _extract_content(self, api_key: str, urls: list[str]) -> dict:
        """
        Extract content from URLs using Tavily Extract API.
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        extract_params = {
            "urls": urls,
            "extract_depth": "basic"
        }
        
        response = requests.post(
            f"{TAVILY_API_URL}/extract",
            json=extract_params,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
