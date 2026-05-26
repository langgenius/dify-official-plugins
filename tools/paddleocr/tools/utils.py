import base64
import logging
import os
import re
from typing import Any, List, Optional, Tuple

import requests
from dify_plugin.file.file import File
from dify_plugin.invocations.file import UploadFileResponse

REQUEST_TIMEOUT = (10, 600)

# Pre-compiled regex patterns for performance
HTML_IMG_PATTERN = re.compile(r'(<img[^>]*src=")([^"]+)(")')

# Template for failed image replacement pattern
FAILED_IMG_TAG_TEMPLATE = r'<img[^>]*src="[^"]*{escaped_path}[^"]*"[^>]*>'


logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def convert_file_type(file_type: str | None) -> int | None:
    """Convert file type string to API parameter value.

    Args:
        file_type: "auto", "pdf", or "image"

    Returns:
        0 for PDF, 1 for image, None for auto
    """
    if file_type == "pdf":
        return 0
    elif file_type == "image":
        return 1
    else:  # "auto" or None
        return None


def normalize_file_input(file_value: Any, file_type: str | None) -> tuple[str, int | None]:
    """Normalize PaddleOCR file input for API payloads.

    Uploaded Dify files are converted to base64 content because the PaddleOCR
    API accepts either a URL or base64-encoded file content in the `file` field.
    Legacy string values are kept unchanged for URL/base64 compatibility.
    """
    if file_value is None or (isinstance(file_value, str) and file_value == ""):
        raise RuntimeError("File is not provided.")

    explicit_file_type = convert_file_type(file_type)

    if isinstance(file_value, File):
        encoded_file = base64.b64encode(file_value.blob).decode("utf-8")
        if explicit_file_type is not None:
            return encoded_file, explicit_file_type
        return encoded_file, infer_file_type(file_value)

    if isinstance(file_value, str):
        return file_value, explicit_file_type

    raise RuntimeError("File must be a Dify file, URL, or base64-encoded string.")


def infer_file_type(file_value: File) -> int | None:
    mime_type = (file_value.mime_type or "").lower()
    if mime_type == "application/pdf":
        return 0
    if mime_type.startswith("image/"):
        return 1

    extension = normalize_extension(file_value.extension)
    if extension is None:
        extension = normalize_extension(os.path.splitext(file_value.filename or "")[1])

    if extension == ".pdf":
        return 0
    if extension in IMAGE_EXTENSIONS:
        return 1

    return None


def normalize_extension(extension: str | None) -> str | None:
    if not extension:
        return None
    extension = extension.lower()
    return extension if extension.startswith(".") else f".{extension}"


def extract_image_urls_from_markdown(markdown: str) -> List[str]:
    """Extract image URLs from markdown"""
    # Match various image URL formats, including relative and absolute paths
    image_pattern = re.compile(r'<img[^>]*src="([^"]*)"[^>]*>', re.IGNORECASE)
    matches = image_pattern.findall(markdown)
    return matches


def download_image_from_url(image_url: str) -> bytes:
    """Download image from URL and return image data and MIME type"""
    try:
        logger.debug(f"Downloading image from URL: {image_url}")
        resp = requests.get(image_url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        logger.debug(
            f"Successfully downloaded image from {image_url}, size: {len(resp.content)} bytes"
        )
        return resp.content
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout downloading image from {image_url}: {e}")
        raise RuntimeError(f"Failed to download image from {image_url}: timeout") from e
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error downloading image from {image_url}: {e}")
        raise RuntimeError(f"Failed to download image from {image_url}: network error") from e
    except Exception as e:
        logger.error(f"Unexpected error downloading image from {image_url}: {e}")
        raise RuntimeError(f"Failed to download image from {image_url}: {e}") from e


def replace_markdown_image_paths(
    markdown: str,
    image_path_map: dict[str, UploadFileResponse],
    failed_images: Optional[List[str]] = None,
) -> str:
    """Replace image paths in HTML img tags with uploaded URLs.

    Handles the PaddleOCR standard image format.
    For failed images (no preview URL available), replaces with placeholder text.
    """
    if failed_images is None:
        failed_images = []

    logger.debug(
        f"Replacing image paths in markdown - {len(image_path_map)} images available, {len(failed_images)} need placeholder"
    )

    # Replace successful images using pre-compiled regex
    replaced_count = 0
    for image_path, upload_response in image_path_map.items():
        if upload_response.preview_url:
            original_markdown = markdown
            markdown = HTML_IMG_PATTERN.sub(
                lambda m: (
                    f"{m.group(1)}{upload_response.preview_url}{m.group(3)}"
                    if m.group(2) == image_path
                    else m.group(0)
                ),
                markdown,
            )
            if markdown != original_markdown:
                replaced_count += 1
                logger.debug(f"Replaced image path {image_path} with {upload_response.preview_url}")

    # Handle images that couldn't get URLs - replace with placeholder
    placeholder_count = 0
    for failed_path in failed_images:
        escaped_path = re.escape(failed_path)
        # Remove entire img tags for failed images using template pattern
        pattern = FAILED_IMG_TAG_TEMPLATE.format(escaped_path=escaped_path)
        original_markdown = markdown
        markdown = re.sub(pattern, "[Image unavailable]", markdown)
        if markdown != original_markdown:
            placeholder_count += 1
            logger.debug(f"Replaced failed image {failed_path} with placeholder")

    logger.debug(
        f"Markdown replacement completed - {replaced_count} URL replacements, {placeholder_count} placeholders"
    )
    return markdown


def process_images_from_result(
    result: dict, tool_instance
) -> Tuple[
    List[UploadFileResponse], dict[str, UploadFileResponse], List[str], List[Tuple[bytes, dict]]
]:
    """Extract and process images from API result

    Args:
        result: API response result
        tool_instance: Tool instance for file operations
    """
    images = []
    image_path_map = {}  # key: image path, value: UploadFileResponse
    failed_images = []  # images that failed to process
    blob_messages = []  # blob messages to yield: [(data, meta), ...]
    image_counter = 0

    logger.debug("Processing images from API result")

    for item in result.get("result", {}).get("layoutParsingResults", []):
        markdown_data = item.get("markdown", {})
        if markdown_data:
            # Get image dictionary {path: url} from markdown
            image_dict = markdown_data.get("images", {})
            if image_dict:
                logger.debug(
                    f"Found {len(image_dict)} images to process: {list(image_dict.keys())}"
                )
            else:
                logger.debug("No images found in this markdown item")

            for image_path, image_url in image_dict.items():
                if image_path in image_path_map:
                    # Already processed this path
                    logger.debug(f"Skipping already processed image: {image_path}")
                    continue

                logger.debug(f"Processing image: {image_path} -> {image_url}")

                image_processed_successfully = False

                try:
                    # Download image first
                    try:
                        image_bytes = download_image_from_url(image_url)
                    except Exception as download_error:
                        logger.warning(
                            f"Failed to download image {image_path} from {image_url}: {download_error}"
                        )
                        # Cannot download - cannot create blob message, mark as failed for markdown
                        failed_images.append(image_path)
                        continue

                    # Upload image to dify with error handling
                    file_name = f"paddleocr_image_{image_counter}.jpg"
                    logger.debug(f"Uploading image {image_path} as {file_name}")

                    try:
                        upload_response = tool_instance.session.file.upload(
                            file_name, image_bytes, "image/jpeg"
                        )
                        images.append(upload_response)
                        image_path_map[image_path] = upload_response
                        image_counter += 1

                        logger.debug(
                            f"Successfully uploaded image {image_path}, preview_url: {upload_response.preview_url}"
                        )

                        # Check if upload was successful but no preview URL
                        if not upload_response.preview_url:
                            logger.warning(
                                f"No preview URL for uploaded image {image_path}, creating blob message as fallback"
                            )
                            blob_messages.append(
                                (image_bytes, {"filename": file_name, "mime_type": "image/jpeg"})
                            )
                            failed_images.append(image_path)
                        else:
                            image_processed_successfully = True

                    except Exception as upload_error:
                        logger.error(f"Failed to upload image {image_path} to dify: {upload_error}")
                        # Create blob message as fallback when upload fails
                        logger.info(
                            f"Creating blob message as fallback for failed upload of {image_path}"
                        )
                        blob_messages.append(
                            (image_bytes, {"filename": file_name, "mime_type": "image/jpeg"})
                        )
                        failed_images.append(image_path)

                except Exception as e:
                    logger.error(f"Unexpected error processing image {image_path}: {e}")
                    failed_images.append(image_path)
                    continue

                if image_processed_successfully:
                    logger.debug(f"Successfully processed image {image_path}")

    logger.info(
        f"Image processing completed - successful: {len(images)}, markdown-failed: {len(failed_images)}, blob-messages: {len(blob_messages)}"
    )
    if failed_images:
        logger.warning(f"Images that failed processing (no URL available): {failed_images}")

    return images, image_path_map, failed_images, blob_messages


def get_markdown_from_result(
    result: dict,
    image_path_map: Optional[dict[str, UploadFileResponse]] = None,
    failed_images: Optional[List[str]] = None,
) -> str:
    """Extract markdown text from result, replace image references if image path mapping is provided"""
    markdown_text_list = []
    for item in result.get("result", {}).get("layoutParsingResults", []):
        markdown_text = item.get("markdown", {}).get("text")
        if markdown_text is not None:
            if image_path_map or failed_images:
                markdown_text = replace_markdown_image_paths(
                    markdown_text, image_path_map or {}, failed_images
                )
            markdown_text_list.append(markdown_text)
    return "\n\n".join(markdown_text_list)


def make_paddleocr_api_request(api_url: str, params: dict, access_token: str) -> dict:
    try:
        logger.debug(f"Making PaddleOCR API request to {api_url}")
        resp = requests.post(
            api_url,
            headers={"Client-Platform": "dify", "Authorization": f"token {access_token}"},
            json=params,
            timeout=REQUEST_TIMEOUT,
        )
        logger.debug(f"PaddleOCR API request completed with status {resp.status_code}")
    except requests.exceptions.Timeout as e:
        logger.error(f"PaddleOCR API request timed out: {e}")
        raise RuntimeError("PaddleOCR API request timed out") from e
    except requests.exceptions.RequestException as e:
        logger.error(f"PaddleOCR API request failed (network error): {e}")
        raise RuntimeError("PaddleOCR API request failed (network error)") from e

    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        status = resp.status_code

        if status in (400, 422):
            try:
                result = resp.json()
                err_code = result.get("errorCode")
                err_msg = result.get("errorMsg")
            except ValueError:
                err_code = None
                err_msg = resp.text or "Bad Request"

            logger.error(f"PaddleOCR API returned {status}: code={err_code}, msg={err_msg}")
            raise RuntimeError(
                f"PaddleOCR API returned {status}: code={err_code}, msg={err_msg}"
            ) from e

        if status in (401, 403):
            logger.error(f"PaddleOCR API authorization failed ({status})")
            raise RuntimeError(f"PaddleOCR API authorization failed ({status})") from e

        if status == 429:
            logger.warning("PaddleOCR API rate limit exceeded (429)")
            raise RuntimeError("PaddleOCR API rate limit exceeded (429)") from e

        if status in (500, 502, 503, 504):
            logger.error(f"PaddleOCR API service unavailable ({status})")
            raise RuntimeError(f"PaddleOCR API service unavailable ({status})") from e

        logger.error(f"PaddleOCR API returned HTTP {status}: {resp.text}")
        raise RuntimeError(f"PaddleOCR API returned HTTP {status}: {resp.text}") from e

    try:
        result = resp.json()
        logger.debug("Successfully parsed PaddleOCR API response")
    except ValueError as e:
        logger.error(f"Failed to decode JSON response from PaddleOCR API: {resp.text}")
        raise RuntimeError(f"Failed to decode JSON response from PaddleOCR API: {resp.text}") from e

    err_code = result.get("errorCode")
    err_msg = result.get("errorMsg")
    if err_code != 0:
        logger.error(f"PaddleOCR API returned error: code={err_code}, msg={err_msg}")
        raise RuntimeError(f"PaddleOCR API returned error: code={err_code}, msg={err_msg}")

    return result
