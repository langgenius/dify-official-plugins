import json
from collections.abc import Generator
from datetime import datetime
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError

from .github_error_handler import handle_github_api_error


class GithubPullReviewsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get reviews on a pull request
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        pull_number = tool_parameters.get("pull_number")
        per_page = tool_parameters.get("per_page", 30)
        credential_type = self.runtime.credential_type

        if not owner:
            yield self.create_text_message("Please input owner")
            return
        if not repo:
            yield self.create_text_message("Please input repo")
            return
        if not pull_number:
            yield self.create_text_message("Please input pull_number")
            return

        if credential_type == CredentialType.API_KEY and "access_tokens" not in self.runtime.credentials:
            yield self.create_text_message("GitHub API Access Tokens is required.")
            return

        if credential_type == CredentialType.OAUTH and "access_tokens" not in self.runtime.credentials:
            yield self.create_text_message("GitHub OAuth Access Tokens is required.")
            return

        access_token = self.runtime.credentials.get("access_tokens")

        # Validate token exists and is not empty
        if not access_token or not access_token.strip():
            yield self.create_text_message("❌ GitHub access token is empty or invalid")
            return

        try:
            headers = {
                "Content-Type": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            s = requests.session()
            api_domain = "https://api.github.com"

            # First, verify PR exists and get its info
            pr_url = f"{api_domain}/repos/{owner}/{repo}/pulls/{int(pull_number)}"
            pr_response = s.request(method="GET", headers=headers, url=pr_url)

            # Debug: Log the request details
            import sys
            print(f"[DEBUG] PR请求: {pr_url}", file=sys.stderr)
            print(f"[DEBUG] PR状态码: {pr_response.status_code}", file=sys.stderr)
            if pr_response.status_code != 200:
                print(f"[DEBUG] PR响应: {pr_response.text[:500]}", file=sys.stderr)

            # Check for authentication issues
            if pr_response.status_code == 401:
                s.close()
                yield self.create_text_message(
                    f"❌ Authentication failed: Invalid or expired GitHub token\n\n"
                    f"Please check your access token is correct and has not expired."
                )
                return
            elif pr_response.status_code == 403:
                s.close()
                error_msg = pr_response.json().get('message', 'Unknown error')
                yield self.create_text_message(
                    f"❌ Access denied: {error_msg}\n\n"
                    f"Your token may not have permission to access this repository.\n"
                    f"For langgenius organization, you may need a fine-grained token."
                )
                return

            if pr_response.status_code != 200:
                s.close()
                yield self.create_text_message(
                    f"❌ Pull request not found: {owner}/{repo}#{pull_number}\n"
                    f"Status: {pr_response.status_code}\n"
                    f"Please verify the owner, repository name, and PR number are correct."
                )
                return

            pr_info = pr_response.json()
            pr_state = pr_info.get('state', '')
            is_draft = pr_info.get('draft', False)
            is_merged = pr_info.get('merged', False)

            # Now get reviews
            url = f"{api_domain}/repos/{owner}/{repo}/pulls/{int(pull_number)}/reviews"
            params = {"per_page": per_page}
            response = s.request(method="GET", headers=headers, url=url, params=params)

            # Debug: Log the reviews request
            print(f"[DEBUG] Reviews请求: {url}", file=sys.stderr)
            print(f"[DEBUG] Reviews状态码: {response.status_code}", file=sys.stderr)
            if response.status_code != 200:
                print(f"[DEBUG] Reviews响应: {response.text[:500]}", file=sys.stderr)

            if response.status_code == 200:
                reviews_data = response.json()

                reviews = []
                state_summary = {
                    "APPROVED": 0,
                    "CHANGES_REQUESTED": 0,
                    "COMMENTED": 0,
                    "PENDING": 0,
                    "DISMISSED": 0,
                }

                for review in reviews_data:
                    state = review.get("state", "")
                    if state in state_summary:
                        state_summary[state] += 1

                    reviews.append({
                        "id": review.get("id"),
                        "user": review.get("user", {}).get("login", ""),
                        "state": state,
                        "body": review.get("body", "") or "",
                        "commit_id": review.get("commit_id", "")[:7] if review.get("commit_id") else "",
                        "submitted_at": datetime.strptime(
                            review.get("submitted_at", ""), "%Y-%m-%dT%H:%M:%SZ"
                        ).strftime("%Y-%m-%d %H:%M:%S") if review.get("submitted_at") else "",
                        "url": review.get("html_url", ""),
                    })

                s.close()

                result = {
                    "pr_info": {
                        "number": pull_number,
                        "state": pr_state,
                        "draft": is_draft,
                        "merged": is_merged,
                    },
                    "total_reviews": len(reviews),
                    "state_summary": state_summary,
                    "reviews": reviews,
                }

                # Add a note if PR is draft or merged
                note = ""
                if is_draft:
                    note = "\n\n⚠️ Note: This is a draft PR."
                elif is_merged:
                    note = "\n\n✅ Note: This PR has been merged."
                elif pr_state == "closed":
                    note = "\n\n❌ Note: This PR is closed (not merged)."

                yield self.create_text_message(json.dumps(result, ensure_ascii=False, indent=2) + note)
            elif response.status_code == 404:
                # PR exists but reviews endpoint returns 404 - this is the Classic Token issue
                s.close()
                yield self.create_text_message(
                    f"❌ Classic Token被组织阻止 - 无法访问 Reviews\n\n"
                    f"PR信息:\n"
                    f"- 仓库: {owner}/{repo}\n"
                    f"- PR号: #{pull_number}\n"
                    f"- 状态: {pr_state}\n"
                    f"- Draft: {is_draft}\n"
                    f"- Merged: {is_merged}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔍 问题原因:\n"
                    f"   langgenius组织启用了安全策略,禁止Classic Token访问reviews端点\n"
                    f"   即使PR存在且公开,Classic Token也会返回404\n\n"
                    f"🔧 解决方案:\n"
                    f"   必须使用 Fine-grained Personal Access Token\n\n"
                    f"📝 操作步骤:\n"
                    f"   1. 访问: https://github.com/settings/tokens?type=beta\n"
                    f"   2. 点击 'Generate new token'\n"
                    f"   3. 配置权限:\n"
                    f"      • Repository access: Public Repositories (read-only)\n"
                    f"      • Permissions: Pull requests (Read-only)\n"
                    f"   4. 生成token后,在Dify插件中更新credentials\n\n"
                    f"⚠️ 注意: Classic Token已被GitHub逐步淘汰,建议所有工具都使用Fine-grained Token\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"API URL: {url}"
                )
                return
            else:
                # Include more debug info in error
                s.close()
                yield self.create_text_message(
                    f"❌ Failed to get reviews for {owner}/{repo}#{pull_number}\n"
                    f"URL: {url}\n"
                    f"Status: {response.status_code}\n"
                    f"Response: {response.text[:500]}"
                )
                return
        except InvokeError as e:
            yield self.create_text_message(f"❌ {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"❌ GitHub API request failed: {e}")
