from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any, Generator
from urllib.parse import parse_qs, urlparse

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from requests import Session
from youtube_transcript_api import YouTubeTranscriptApi, formatters
from youtube_transcript_api.proxies import GenericProxyConfig


class YouTubeTranscriptTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the YouTube transcript tool.
        """
        try:
            video_input = tool_parameters["video_id"]
            languages = self._parse_languages(tool_parameters.get("language"))
            output_format = tool_parameters.get("format", "text")
            preserve_formatting = tool_parameters.get("preserve_formatting", False)
            proxy = tool_parameters.get("proxy")
            cookies = tool_parameters.get("cookies")
            video_id = self._extract_video_id(video_input)

            try:
                api = self._build_api(proxy=proxy, cookies=cookies)
                transcript = self._fetch_transcript(
                    api,
                    video_id,
                    languages=languages,
                    preserve_formatting=preserve_formatting,
                )
                formatted_transcript = self._format_transcript(
                    transcript, output_format
                )
                yield self.create_text_message(text=formatted_transcript)
            except Exception as e:
                yield self.create_text_message(
                    text=f"Error getting transcript: {str(e)}"
                )
        except Exception as e:
            yield self.create_text_message(text=f"Error processing request: {str(e)}")

    def _build_api(
        self, proxy: str | None, cookies: str | None
    ) -> YouTubeTranscriptApi:
        proxy_config = GenericProxyConfig(https_url=proxy) if proxy else None
        http_client = None
        if cookies:
            cookie_path = Path(cookies).expanduser()
            cookie_jar = MozillaCookieJar(str(cookie_path))
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
            http_client = Session()
            http_client.cookies = cookie_jar
        return YouTubeTranscriptApi(proxy_config=proxy_config, http_client=http_client)

    def _fetch_transcript(
        self,
        api: YouTubeTranscriptApi,
        video_id: str,
        languages: list[str] | None,
        preserve_formatting: bool,
    ):
        if languages:
            try:
                return api.fetch(
                    video_id,
                    languages=languages,
                    preserve_formatting=preserve_formatting,
                )
            except Exception:
                transcript_list = api.list(video_id)
                try:
                    transcript = transcript_list.find_transcript(languages)
                except Exception:
                    try:
                        transcript = transcript_list.find_transcript(["en"])
                    except Exception:
                        transcript = next(iter(transcript_list))
                    transcript = transcript.translate(languages[0])
                return transcript.fetch(preserve_formatting=preserve_formatting)

        try:
            return api.fetch(video_id, preserve_formatting=preserve_formatting)
        except Exception:
            transcript_list = api.list(video_id)
            transcript = next(iter(transcript_list))
            return transcript.fetch(preserve_formatting=preserve_formatting)

    def _format_transcript(self, transcript, output_format: str) -> str:
        formatter_class = {
            "json": formatters.JSONFormatter,
            "pretty": formatters.PrettyPrintFormatter,
            "srt": formatters.SRTFormatter,
            "vtt": formatters.WebVTTFormatter,
        }.get(output_format)
        if formatter_class:
            return formatter_class().format_transcript(transcript)

        raw_transcript = (
            transcript.to_raw_data()
            if hasattr(transcript, "to_raw_data")
            else transcript
        )
        return " ".join(entry["text"] for entry in raw_transcript)

    def _parse_languages(self, language: str | None) -> list[str] | None:
        if not language:
            return None
        languages = [item.strip() for item in language.split(",") if item.strip()]
        return languages or None

    def _extract_video_id(self, video_input: str) -> str:
        """
        Extract video ID from a URL, or return as-is if already an ID.
        """
        video_input = video_input.strip()
        if "youtube.com" not in video_input and "youtu.be" not in video_input:
            return video_input

        if not video_input.startswith(("http://", "https://")):
            video_input = "https://" + video_input

        parsed_url = urlparse(video_input)
        if "youtu.be" in parsed_url.netloc:
            return parsed_url.path.strip("/").split("/")[0]

        query_video_id = parse_qs(parsed_url.query).get("v")
        if query_video_id:
            return query_video_id[0]

        path_parts = [part for part in parsed_url.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] in {"embed", "live", "shorts", "v"}:
            return path_parts[1]

        return video_input
