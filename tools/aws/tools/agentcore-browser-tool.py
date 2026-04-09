import json
import time
import base64
import asyncio
import nest_asyncio
from collections.abc import Generator
from typing import Any, Optional, Dict
import os
import tempfile
from pathlib import Path

nest_asyncio.apply()

from bedrock_agentcore.tools.browser_client import BrowserClient, browser_session
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from playwright.async_api import async_playwright

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
import traceback

from provider.utils import ParameterStoreManager

class AgentcoreBrowserToolTool(Tool):
    # 基于 browser_session_id 的资源管理字典
    _sessions = {}  # {browser_session_id: {"browser": ..., "page": ..., "playwright": ...}}
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._setup_temp_dir()
    
    def _setup_temp_dir(self):
        """设置 Playwright 临时目录"""
        try:
            # 创建用户专用的临时目录
            user_temp = Path.home() / "tmp" / "playwright"
            user_temp.mkdir(parents=True, exist_ok=True)
            
            # 设置权限
            os.chmod(user_temp, 0o755)
            
            # 设置环境变量
            os.environ["TMPDIR"] = str(user_temp)
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(user_temp / "browsers")
            
        except Exception as e:
            print(f"Warning: Could not setup custom temp dir: {e}")
    
    def _get_session(self, session_id: str) -> dict:
        """获取指定 session_id 的资源"""
        return self._sessions.get(session_id, {})
    
    def _set_session(self, session_id: str, browser, page, playwright):
        """设置指定 session_id 的资源"""
        self._sessions[session_id] = {
            "browser": browser,
            "page": page,
            "playwright": playwright
        }

    async def _init_browser_session(self, browser_session_id:str, aws_region:str) -> dict:
        """Initialize AWS AgentCore Browser session"""
        try:
            session = self._get_session(browser_session_id)
            
            if not session:
                print("start to initialize browser session...")

                # Get session info from Parameter Store
                param_manager = ParameterStoreManager(aws_region)
                session_data = param_manager.get_parameter(f"/browser-session/{browser_session_id}", as_dict=True)
                
                if not session_data:
                    raise InvokeError(f"Browser session {browser_session_id} not found in Parameter Store")
                
                ws_url = session_data.get("ws_url")
                ws_headers = session_data.get("ws_headers")
                
                if not ws_url or not ws_headers:
                    raise InvokeError(f"Invalid session data for {browser_session_id}")
            
                # Use Playwright to connect to the remote browser
                playwright = await async_playwright().start()
            
                try:
                    browser = await playwright.chromium.connect_over_cdp(
                        endpoint_url=ws_url,
                        headers=ws_headers
                    )
                
                    context = browser.contexts[0]
                    page = context.pages[0]
                    
                    self._set_session(browser_session_id, browser, page, playwright)

                    print("finish initializing browser session.")
                
                except Exception as e:
                    # 如果连接失败，确保playwright被清理
                    if playwright:
                        await playwright.stop()

                    print(f"connect_over_cdp fails due to {str(e)}")
                    raise
            else:
                print("reuse existing browser session.")

            # Debug information
            session = self._get_session(browser_session_id)
            session_info = {
                "success": True,
                "page_id": id(session.get("page")),
                "browser_id": id(session.get("browser"))
            }
            
            return session_info
            
        except Exception as e:
            print(f"init_browser_session fails due to {str(e)}")
            await self._cleanup_browser(browser_session_id)
            return {
                "success": False,
                "error": f"Failed to initialize browser session: {str(e)}",
                "status": "Connect to Browser session failed"
            }
    
    async def _cleanup_browser(self, session_id: str = None):
        """Clean up the browser session and all resources"""
        try:
            if not session_id:
                return
                
            session = self._get_session(session_id)
            if session:
                if session.get("browser"):
                    await session["browser"].close()
                if session.get("playwright"):
                    await session["playwright"].stop()
                del self._sessions[session_id]
        except Exception:
            pass
    
    async def _browse_url(self, browser_session_id:str, url: str, wait_time: int = 3) -> dict:
        """Browse a URL using existing browser session"""
        try:
            session = self._get_session(browser_session_id)
            page = session.get("page")
            
            if not page:
                return {
                    "success": False,
                    "error": "Browser session not initialized. Please call init_browser_session first.",
                    "status": "No active browser session"
                }
            
            # Navigate to URL
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # Wait for additional loading
            await asyncio.sleep(wait_time)
            
            # Get page information
            title = await page.title()
            current_url = page.url
            content = await page.inner_text("body")
            
            # Limit content length
            if len(content) > 5000:
                content = content[:5000] + "... [Content truncated]"
            
            return {
                "success": True,
                "title": title,
                "url": current_url,
                "content": content,
                "status": "Page loaded successfully"
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to browse URL: {str(e)}",
                "status": "Error occurred while browsing"
            }
    
    async def _search_web(self, browser_session_id:str, query: str, wait_time: int = 3) -> dict:
        """Perform web search using existing browser session"""
        try:
            session = self._get_session(browser_session_id)
            page = session.get("page")
            
            if not page:
                return {
                    "success": False,
                    "error": "Browser session not initialized. Please call init_browser_session first.",
                    "status": "No active browser session"
                }
            
            # Navigate to Google
            await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)
            
            # Wait for search box to be available and fill it
            search_box = page.locator('input[name="q"]')
            await search_box.wait_for(state="visible", timeout=60000)
            await search_box.fill(query, timeout=10000)
            await search_box.press("Enter")
            
            # Wait for search results
            await page.wait_for_selector('div.g', timeout=10000)
            await asyncio.sleep(wait_time)
            
            # Extract search results
            results = []
            search_results = await page.locator('div.g').all()
            
            for i, result in enumerate(search_results[:10]):
                try:
                    title_element = result.locator('h3').first
                    link_element = result.locator('a').first
                    snippet_element = result.locator('span').first
                    
                    if await title_element.count() > 0 and await link_element.count() > 0:
                        title = await title_element.inner_text()
                        url = await link_element.get_attribute('href')
                        snippet = await snippet_element.inner_text() if await snippet_element.count() > 0 else ''
                        
                        results.append({
                            "title": title,
                            "url": url,
                            "snippet": snippet
                        })
                except:
                    continue
            
            return {
                "success": True,
                "query": query,
                "results": results,
                "status": f"Found {len(results)} search results"
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to perform web search: {str(e)}",
                "status": "Error occurred during search"
            }
    
    async def _extract_content(self, browser_session_id:str, url: str = None, wait_time: int = 3) -> dict:
        """Extract structured content using existing browser session"""
        try:
            session = self._get_session(browser_session_id)
            page = session.get("page")
            
            if not page:
                return {
                    "success": False,
                    "error": "Browser session not initialized. Please call init_browser_session first.",
                    "status": "No active browser session"
                }
            
            # Navigate to URL if provided
            if url:
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(wait_time)
            
            # Extract structured content
            content = {
                "title": await page.title(),
                "url": page.url,
                "headings": [],
                "links": [],
                "images": [],
                "text_content": ""
            }
            
            # Extract headings
            for i in range(1, 7):
                headings = await page.locator(f'h{i}').all()
                for heading in headings:
                    try:
                        text = (await heading.inner_text()).strip()
                        if text:
                            content["headings"].append({
                                "level": i,
                                "text": text
                            })
                    except:
                        continue
            
            # Extract links (limit to 20)
            links = (await page.locator('a[href]').all())[:20]
            for link in links:
                try:
                    text = (await link.inner_text()).strip()
                    href = await link.get_attribute('href')
                    if text and href:
                        content["links"].append({
                            "text": text,
                            "url": href
                        })
                except:
                    continue
            
            # Extract images (limit to 10)
            images = (await page.locator('img[src]').all())[:10]
            for img in images:
                try:
                    src = await img.get_attribute('src')
                    alt = await img.get_attribute('alt') or ''
                    if src:
                        content["images"].append({
                            "src": src,
                            "alt": alt
                        })
                except:
                    continue
            
            # Extract clean text content
            text_content = await page.inner_text('body')
            if len(text_content) > 3000:
                text_content = text_content[:3000] + '... [Content truncated]'
            
            content["text_content"] = text_content
            
            return {
                "success": True,
                "content": content,
                "status": "Content extracted successfully"
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to extract content: {str(e)}",
                "status": "Error occurred while extracting content"
            }
    
    async def _fill_form(self, browser_session_id:str, url: str = None, form_data: str = "{}", wait_time: int = 3) -> dict:
        """Fill form fields using existing browser session"""
        try:
            session = self._get_session(browser_session_id)
            page = session.get("page")
            
            if not page:
                return {
                    "success": False,
                    "error": "Browser session not initialized. Please call init_browser_session first.",
                    "status": "No active browser session"
                }
            
            # Parse form data JSON
            try:
                form_fields = json.loads(form_data)
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "error": "Invalid JSON format for form_data",
                    "status": "JSON parsing error"
                }
            
            # Navigate to URL if provided
            if url:
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(wait_time)
            
            filled_fields = []
            errors = []
            
            for field_name, field_value in form_fields.items():
                try:
                    # Try different selectors to find the field
                    selectors = [
                        f"input[name='{field_name}']",
                        f"input[id='{field_name}']",
                        f"textarea[name='{field_name}']",
                        f"textarea[id='{field_name}']",
                        f"select[name='{field_name}']",
                        f"select[id='{field_name}']"
                    ]
                    
                    field_found = False
                    for selector in selectors:
                        try:
                            element = page.locator(selector)
                            if await element.count() > 0:
                                await element.fill(str(field_value))
                                filled_fields.append(field_name)
                                field_found = True
                                break
                        except:
                            continue
                    
                    if not field_found:
                        errors.append(f"Field '{field_name}' not found")
                        
                except Exception as e:
                    errors.append(f"Error filling field '{field_name}': {str(e)}")
            
            return {
                "success": len(filled_fields) > 0,
                "filled_fields": filled_fields,
                "errors": errors,
                "status": f"Filled {len(filled_fields)} fields, {len(errors)} errors"
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fill form: {str(e)}",
                "status": "Error occurred while filling form"
            }
    
    async def _execute_script(self, browser_session_id:str, url: str = None, script: str = "", wait_time: int = 3) -> dict:
        """Execute JavaScript on a webpage using existing browser session"""
        try:
            session = self._get_session(browser_session_id)
            page = session.get("page")
            
            if not page:
                return {
                    "success": False,
                    "error": "Browser session not initialized. Please call init_browser_session first.",
                    "status": "No active browser session"
                }
            
            # Navigate to URL if provided
            if url:
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(wait_time)
            
            # Execute the script
            result = await page.evaluate(script)
            
            return {
                "success": True,
                "result": result,
                "status": "Script executed successfully"
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to execute script: {str(e)}",
                "status": "Error occurred while executing script"
            }

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        
        try:
            action = tool_parameters.get("action")
            browser_session_id = tool_parameters.get("browser_session_id")
            aws_region = tool_parameters.get("aws_region", "us-west-2")
             
            url = tool_parameters.get("url", "")
            query = tool_parameters.get("query", "")
            form_data = tool_parameters.get("form_data", "{}")
            script = tool_parameters.get("script", "")
            wait_time = int(tool_parameters.get("wait_time", 3))

            if not browser_session_id:
                raise InvokeError(f"browser_session_id is missing.")

            asyncio.run(self._init_browser_session(browser_session_id, aws_region))
            
            if action == "browse_url":
            
                if not url:
                    yield self.create_json_message({
                        "success": False,
                        "error": "URL is required for browse_url action"
                    })
                    return
                result = asyncio.run(self._browse_url(browser_session_id, url, wait_time))
                
            elif action == "search_web":
            
                if not query:
                    yield self.create_json_message({
                        "success": False,
                        "error": "Query is required for search_web action"
                    })
                    return
                result = asyncio.run(self._search_web(browser_session_id, query, wait_time))
                
            elif action == "extract_content":
            
                result = asyncio.run(self._extract_content(browser_session_id, url, wait_time))
                
            elif action == "fill_form":
            
                result = asyncio.run(self._fill_form(browser_session_id, url, form_data, wait_time))
                
            elif action == "execute_script":
            
                if not script:
                    yield self.create_json_message({
                        "success": False,
                        "error": "Script is required for execute_script action"
                    })
                    return
                result = asyncio.run(self._execute_script(browser_session_id, url, script, wait_time))
                
            else:
                yield self.create_json_message({
                    "success": False,
                    "error": f"Unknown action: {action}. Supported actions: init_browser_session, browse_url, search_web, extract_content, fill_form, execute_script, close_browser_session"
                })
                return
            
            yield self.create_json_message(result)
            
        except Exception as e:
            traceback.print_stack()
            yield self.create_json_message({
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "status": "Tool execution failed"
            })
