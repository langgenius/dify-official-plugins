from dify_plugin import Plugin, DifyPluginEnv

plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))

if __name__ == '__main__':
    plugin.run()

import requests
from dify_plugin_sdk import BasePlugin  # Adjust import based on actual SDK

class GitHubPlugin(BasePlugin):
    def __init__(self, config):
        self.api_key = config.get("api_key")
        self.api_version = config.get("api_version", "2022-11-28")
        if not self.api_key:
            raise ValueError("GitHub API key is missing")

    def github_repositories(self, query, top_n):
        """
        Query GitHub repositories using the search API.
        Args:
            query (str): Search query (e.g., "machine learning").
            top_n (int): Number of results to return.
        Returns:
            dict: Repository search results or error message.
        """
        url = "https://api.github.com/search/repositories"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.api_version
        }
        params = {"q": query, "per_page": top_n}

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()  # Raise exception for 4xx/5xx errors
            data = response.json()
            results = [
                {
                    "name": item["name"],
                    "full_name": item["full_name"],
                    "html_url": item["html_url"],
                    "description": item["description"]
                }
                for item in data.get("items", [])[:top_n]
            ]
            return {"github_repositories": {"items": results}}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [401, 403]:
                return {"github_repositories": "Invalid GitHub API key or insufficient permissions"}
            return {"github_repositories": f"GitHub API error: {str(e)}"}
        except Exception as e:
            return {"github_repositories": f"Plugin error: {str(e)}"}
