import requests
from typing import Any, Generator, List, Dict
from dify_plugin.entities.tool import ToolInvokeMessage


def process_images(
    tool: Any, image_urls: List[str]
) -> Generator[ToolInvokeMessage, None, None]:
    """Downloads images from a list of URLs and yields them as tool messages."""
    for image_url in image_urls:
        if not image_url:
            continue

        try:
            image_response = requests.get(image_url, timeout=10)
            image_response.raise_for_status()

            content_type = image_response.headers.get("Content-Type", "image/jpeg")
            filename = image_url.split("/")[-1].split("?")[0]

            yield tool.create_blob_message(
                blob=image_response.content,
                meta={
                    "mime_type": content_type,
                    "filename": filename,
                    "alt_text": "Tavily result image",
                },
            )
        except Exception as e:
            print(f"Failed to download image {image_url}: {str(e)}")


def process_favicons(
    tool: Any, results: List[Dict]
) -> Generator[ToolInvokeMessage, None, None]:
    """Downloads favicons from results and yields them as tool messages."""
    for idx, result in enumerate(results):
        if not result.get("favicon"):
            continue

        favicon_url = result["favicon"]
        try:
            favicon_response = requests.get(favicon_url, timeout=10)
            favicon_response.raise_for_status()

            content_type = favicon_response.headers.get("Content-Type", "image/png")
            filename = favicon_url.split("/")[-1].split("?")[0]
            if not filename or "." not in filename:
                if "svg" in content_type:
                    filename = f"favicon_{idx}.svg"
                elif "png" in content_type:
                    filename = f"favicon_{idx}.png"
                elif "jpeg" in content_type or "jpg" in content_type:
                    filename = f"favicon_{idx}.jpg"
                elif "gif" in content_type:
                    filename = f"favicon_{idx}.gif"
                elif "webp" in content_type:
                    filename = f"favicon_{idx}.webp"
                else:
                    filename = f"favicon_{idx}.ico"

            alt_text = (
                f"Favicon for {result.get('title') or result.get('url', 'website')}"
            )
            yield tool.create_blob_message(
                blob=favicon_response.content,
                meta={
                    "mime_type": content_type,
                    "filename": filename,
                    "alt_text": alt_text,
                },
            )
        except Exception as e:
            print(f"Failed to download favicon {favicon_url}: {str(e)}")
