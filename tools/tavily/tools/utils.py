import requests
from typing import Any, Generator, List, Dict
from dify_plugin.entities.tool import ToolInvokeMessage


def process_search_images(
    tool: Any, images: List
) -> Generator[ToolInvokeMessage, None, None]:
    """Downloads images from search results and yields them as tool messages."""
    for image in images:
        if isinstance(image, dict):
            image_url = image.get("url")
            alt_text = image.get("description", "Tavily search result image")
        elif isinstance(image, str):
            image_url = image
            alt_text = "Tavily search result image"
        else:
            continue  # Skip unexpected formats

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
                    "alt_text": alt_text,
                },
            )
        except Exception as e:
            print(f"Failed to download image {image_url}: {str(e)}")


def process_search_favicons(
    tool: Any, results: List[Dict]
) -> Generator[ToolInvokeMessage, None, None]:
    """Downloads favicons from search results and yields them as tool messages."""
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

            alt_text = f"Favicon for {result.get('title', 'website')}"
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


def process_extract_images(
    tool: Any, results: List[Dict]
) -> Generator[ToolInvokeMessage, None, None]:
    """Downloads images from extracted results and yields them as tool messages."""
    for result in results:
        if "images" in result and result["images"]:
            for image_url in result["images"]:
                try:
                    image_response = requests.get(image_url, timeout=10)
                    image_response.raise_for_status()
                    content_type = image_response.headers.get(
                        "Content-Type", "image/jpeg"
                    )
                    filename = image_url.split("/")[-1].split("?")[0]
                    alt_text = f"Image from {result.get('url', 'source')}"

                    yield tool.create_blob_message(
                        blob=image_response.content,
                        meta={
                            "mime_type": content_type,
                            "filename": filename,
                            "alt_text": alt_text,
                        },
                    )
                except Exception as e:
                    print(f"Failed to download image {image_url}: {str(e)}")


def process_extract_favicons(
    tool: Any, results: List[Dict]
) -> Generator[ToolInvokeMessage, None, None]:
    """Downloads favicons from extracted results and yields them as tool messages."""
    for result in results:
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
                    filename = "favicon.svg"
                elif "png" in content_type:
                    filename = "favicon.png"
                elif "jpeg" in content_type or "jpg" in content_type:
                    filename = "favicon.jpg"
                elif "gif" in content_type:
                    filename = "favicon.gif"
                elif "webp" in content_type:
                    filename = "favicon.webp"
                else:
                    filename = "favicon.ico"

            alt_text = f"Favicon for {result.get('url')}"
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
