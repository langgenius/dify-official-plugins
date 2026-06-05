import base64
import json
import logging
import os
import re
import time
import tempfile
from typing import Any, List, Optional, Tuple
from urllib.parse import urlparse

from dify_plugin.file.file import File
from dify_plugin.invocations.file import UploadFileResponse

# Pre-compiled regex patterns for performance
HTML_IMG_PATTERN = re.compile(r'(<img[^>]*src=")([^"]+)(")')
FAILED_IMG_TAG_TEMPLATE = r'<img[^>]*src="[^"]*{escaped_path}[^"]*"[^>]*>'


logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def camel_to_snake(name: str) -> str:
    """Convert camelCase or PascalCase to snake_case.

    Args:
        name: camelCase or PascalCase string

    Returns:
        snake_case string
    """
    # Handle camelCase
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    # Handle PascalCase
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def extract_base_url(api_url: str) -> str:
    """Extract base URL from full API URL.

    The SDK requires a base URL (e.g., https://example.com)
    but users provide the full API URL (e.g., https://example.com/ocr).
    This function extracts the base URL by removing the endpoint path.

    Args:
        api_url: Full API URL

    Returns:
        Base URL without endpoint path
    """
    parsed = urlparse(api_url)
    # Remove common PaddleOCR endpoints
    path = parsed.path.rstrip("/")
    if path in ("", "/ocr", "/layout-parsing", "/paddleocr"):
        path = ""
    return f"{parsed.scheme}://{parsed.netloc}{path}"


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
    else:
        return None


def normalize_file_input(file_value: Any, file_type: str | None) -> Tuple[str, bool, int | None]:
    """Normalize PaddleOCR file input.

    Returns:
        A tuple of (input_value, is_temp_file, file_type_code):
        - input_value: URL, file path (temp or regular), or base64 string
        - is_temp_file: True if the value is a temporary file path that should be deleted
        - file_type_code: 0 for PDF, 1 for image, None for auto
    """
    if file_value is None or (isinstance(file_value, str) and file_value == ""):
        raise RuntimeError("File is not provided.")

    explicit_file_type = convert_file_type(file_type)

    if isinstance(file_value, File):
        encoded_file = base64.b64encode(file_value.blob).decode("utf-8")
        temp_file = base64_to_temp_file(encoded_file, infer_file_extension(file_value))
        file_type_code = explicit_file_type if explicit_file_type is not None else infer_file_type(file_value)
        return temp_file, True, file_type_code

    if isinstance(file_value, str):
        # Check if it's a URL
        if file_value.startswith(("http://", "https://")):
            return file_value, False, explicit_file_type
        # Check if it's a file path (AI reviewer suggestion: check file path before base64 validation)
        if os.path.exists(file_value):
            return file_value, False, explicit_file_type
        # Check if it's base64 (data URL or raw)
        if file_value.startswith("data:") or is_likely_base64(file_value):
            temp_file = base64_to_temp_file(extract_base64(file_value))
            return temp_file, True, explicit_file_type
        # It's a file path (doesn't exist, but could be relative path)
        return file_value, False, explicit_file_type

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


def infer_file_extension(file_value: File) -> str:
    mime_type = (file_value.mime_type or "").lower()
    if mime_type == "application/pdf":
        return ".pdf"
    if mime_type.startswith("image/"):
        ext = mime_type.split("/")[-1]
        return f".{ext}"

    extension = normalize_extension(file_value.extension)
    if extension is None:
        extension = normalize_extension(os.path.splitext(file_value.filename or "")[1])

    return extension if extension else ".png"


def normalize_extension(extension: str | None) -> str | None:
    if not extension:
        return None
    extension = extension.lower()
    return extension if extension.startswith(".") else f".{extension}"


def extract_base64(data_url: str) -> str:
    if data_url.startswith("data:"):
        return data_url.split(",", 1)[1]
    return data_url


def is_likely_base64(s: str) -> bool:
    if len(s) < 32:
        return False
    try:
        base64.b64decode(s, validate=True)
        return True
    except Exception:
        return False


def base64_to_temp_file(base64_str: str, suffix: str = ".png") -> str:
    """Save base64 string to a temporary file.

    Args:
        base64_str: Base64 encoded string
        suffix: File extension suffix

    Returns:
        Path to the temporary file
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(base64.b64decode(base64_str))
        return f.name


def bytes_to_temp_file(data: bytes, suffix: str = ".png") -> str:
    """Save bytes directly to a temporary file (AI reviewer suggestion).

    Args:
        data: Raw bytes data
        suffix: File extension suffix

    Returns:
        Path to the temporary file
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(data)
        return f.name


def cleanup_temp_file(file_path: str, is_temp: bool) -> None:
    """Clean up temporary file if it exists and is marked as temporary.

    Args:
        file_path: Path to the file
        is_temp: True if the file is a temporary file that should be deleted
    """
    if is_temp and file_path and os.path.exists(file_path):
        try:
            os.unlink(file_path)
        except Exception as e:
            logger.warning(f"Failed to clean up temporary file {file_path}: {e}")


def extract_image_urls_from_markdown(markdown: str) -> List[str]:
    """Extract image URLs from markdown"""
    image_pattern = re.compile(r'<img[^>]*src="([^"]*)"[^>]*>', re.IGNORECASE)
    matches = image_pattern.findall(markdown)
    return matches


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
    image_path_map = {}
    failed_images = []
    blob_messages = []
    image_counter = 0

    logger.debug("Processing images from API result")

    for item in result.get("result", {}).get("layoutParsingResults", []):
        markdown_data = item.get("markdown", {})
        if markdown_data:
            image_dict = markdown_data.get("images", {})
            if image_dict:
                logger.debug(f"Found {len(image_dict)} images to process: {list(image_dict.keys())}")
            else:
                logger.debug("No images found in this markdown item")

            for image_path, image_url in image_dict.items():
                if image_path in image_path_map:
                    logger.debug(f"Skipping already processed image: {image_path}")
                    continue

                logger.debug(f"Processing image: {image_path} -> {image_url}")

                image_processed_successfully = False

                try:
                    try:
                        image_bytes = download_image_from_url(image_url)
                    except Exception as download_error:
                        logger.warning(
                            f"Failed to download image {image_path} from {image_url}: {download_error}"
                        )
                        failed_images.append(image_path)
                        continue

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


def download_image_from_url(image_url: str) -> bytes:
    """Download image from URL and return image data and MIME type"""
    import requests

    try:
        logger.debug(f"Downloading image from URL: {image_url}")
        resp = requests.get(image_url, timeout=(10, 600))
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


# ==================== HTTP Async Job API Implementation ====================

DEFAULT_BASE_URL = "https://paddleocr.aistudio-app.com"
API_PATH = "/api/v2/ocr/jobs"
DEFAULT_REQUEST_TIMEOUT = 300.0
DEFAULT_POLL_TIMEOUT = 600.0
DEFAULT_INITIAL_INTERVAL = 3.0
DEFAULT_MULTIPLIER = 1.5
DEFAULT_MAX_INTERVAL = 15.0


def get_sdk_client(access_token: str, base_url: str | None = None) -> dict[str, Any]:
    """Get PaddleOCR API client configuration.

    Args:
        access_token: AI Studio access token
        base_url: Base URL (optional, uses SDK default if not provided)

    Returns:
        Configuration dict with token, base_url, headers
    """
    # If base_url is provided, extract it (in case user passed full API URL)
    if base_url:
        base_url = extract_base_url(base_url)
    else:
        base_url = DEFAULT_BASE_URL

    return {
        "token": access_token,
        "base_url": base_url.rstrip("/"),
        "headers": {
            "Authorization": f"Bearer {access_token}",
            "Client-Platform": "dify",
        },
    }


def build_ocr_options(params: dict[str, Any]) -> dict[str, Any]:
    """Build OCR options dict from parameters using dynamic conversion.

    Args:
        params: Tool parameters

    Returns:
        Options dict with snake_case keys
    """
    options_dict = {}
    for api_name, value in params.items():
        if value is None:
            continue
        # Convert camelCase to snake_case
        option_name = camel_to_snake(api_name)
        options_dict[option_name] = value
    return options_dict


def build_pp_structure_v3_options(params: dict[str, Any]) -> dict[str, Any]:
    """Build PPStructureV3 options dict from parameters using dynamic conversion.

    Args:
        params: Tool parameters

    Returns:
        Options dict with snake_case keys
    """
    options_dict = {}
    for api_name, value in params.items():
        if value is None:
            continue
        # Convert camelCase to snake_case
        option_name = camel_to_snake(api_name)
        # Handle markdownIgnoreLabels conversion
        if api_name == "markdownIgnoreLabels" and isinstance(value, str):
            value = [label.strip() for label in value.split(",") if label.strip()]
        options_dict[option_name] = value
    return options_dict


def build_paddleocr_vl_options(params: dict[str, Any]) -> dict[str, Any]:
    """Build PaddleOCRVLOptions dict from parameters using dynamic conversion.

    Args:
        params: Tool parameters

    Returns:
        Options dict with snake_case keys
    """
    options_dict = {}
    for api_name, value in params.items():
        if value is None:
            continue
        # Handle promptLabel conversion - skip if "undefined"
        if api_name == "promptLabel" and value == "undefined":
            continue
        # Convert camelCase to snake_case
        option_name = camel_to_snake(api_name)
        # Handle markdownIgnoreLabels conversion
        if api_name == "markdownIgnoreLabels" and isinstance(value, str):
            value = [label.strip() for label in value.split(",") if label.strip()]
        options_dict[option_name] = value
    return options_dict


def _submit_job(
    model: str,
    file_url: str | None,
    file_path: str | None,
    options: dict[str, Any],
    base_url: str,
    headers: dict[str, str],
) -> str:
    """Submit job and return job_id.

    Args:
        model: Model name (e.g., "PP-OCRv5", "PP-StructureV3", "PaddleOCR-VL-1.6")
        file_url: URL of the file (if using URL input)
        file_path: Path to the file (if using file input)
        options: Optional payload parameters
        base_url: Base API URL
        headers: Request headers

    Returns:
        job_id string

    Raises:
        RuntimeError: If submission fails
    """
    import requests

    jobs_url = f"{base_url}{API_PATH}"

    try:
        if file_url:
            # Submit with URL
            body = {
                "fileUrl": file_url,
                "model": model,
                "optionalPayload": options,
            }
            resp = requests.post(jobs_url, json=body, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT)
        else:
            # Submit with file
            data = {
                "model": model,
                "optionalPayload": json.dumps(options),
            }
            with open(file_path, "rb") as f:
                resp = requests.post(
                    jobs_url, data=data, files={"file": f}, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT
                )
    except requests.Timeout as e:
        raise RuntimeError(f"Request timed out: {e}") from e
    except requests.ConnectionError as e:
        raise RuntimeError(f"Connection failed: {e}") from e

    if not 200 <= resp.status_code < 300:
        try:
            payload = resp.json()
            msg = payload.get("msg") or payload.get("message") or payload.get("error") or resp.text
        except ValueError:
            msg = resp.text
        raise RuntimeError(f"Job submission failed (HTTP {resp.status_code}): {msg}")

    try:
        payload = resp.json()
        job_id = payload.get("data", {}).get("jobId") or payload.get("jobId")
        if not job_id:
            raise RuntimeError(f"Job ID not found in response: {payload}")
        return job_id
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"Failed to parse job submission response: {e}") from e


def _poll_job(
    job_id: str,
    base_url: str,
    headers: dict[str, str],
    max_wait_time: float = DEFAULT_POLL_TIMEOUT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Poll job until done, return (jsonl_data, status_data).

    Args:
        job_id: Job ID
        base_url: Base API URL
        headers: Request headers
        max_wait_time: Maximum wait time in seconds

    Returns:
        Tuple of (jsonl_data list, status_data dict)

    Raises:
        RuntimeError: If polling fails or job fails
    """
    import requests

    jobs_url = f"{base_url}{API_PATH}"
    status_url = f"{jobs_url}/{job_id}"

    interval = DEFAULT_INITIAL_INTERVAL
    start = time.monotonic()
    deadline = start + max_wait_time

    while True:
        now = time.monotonic()
        if now >= deadline:
            raise RuntimeError(f"Job {job_id} timed out after {max_wait_time:.1f} seconds")

        try:
            resp = requests.get(status_url, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT)
        except requests.Timeout as e:
            raise RuntimeError(f"Request timed out: {e}") from e
        except requests.ConnectionError as e:
            raise RuntimeError(f"Connection failed: {e}") from e

        if not 200 <= resp.status_code < 300:
            try:
                payload = resp.json()
                msg = payload.get("msg") or payload.get("message") or payload.get("error") or resp.text
            except ValueError:
                msg = resp.text
            raise RuntimeError(f"Poll failed (HTTP {resp.status_code}): {msg}")

        try:
            data = resp.json()
            state = data.get("data", {}).get("state") or data.get("state")
        except (ValueError, KeyError) as e:
            raise RuntimeError(f"Failed to parse poll response: {e}") from e

        if state == "done":
            # Get result URL
            result_json_url = data.get("data", {}).get("resultJsonUrl") or data.get("resultJsonUrl")
            if not result_json_url:
                raise RuntimeError(f"Result URL not found in response: {data}")

            # Fetch JSONL result
            try:
                resp = requests.get(result_json_url, timeout=DEFAULT_REQUEST_TIMEOUT)
                resp.raise_for_status()
            except requests.Timeout as e:
                raise RuntimeError(f"Result download timed out: {e}") from e
            except requests.ConnectionError as e:
                raise RuntimeError(f"Result download failed: {e}") from e

            # Parse JSONL
            lines = resp.text.strip().split("\n")
            jsonl_data = []
            for line in lines:
                line = line.strip()
                if line:
                    try:
                        jsonl_data.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        raise RuntimeError(f"Malformed JSONL result: {e}") from e

            return jsonl_data, data

        if state == "failed":
            error_msg = data.get("data", {}).get("errorMsg") or data.get("errorMsg") or "Unknown error"
            raise RuntimeError(f"Job {job_id} failed: {error_msg}")

        # Continue polling
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"Job {job_id} timed out after {max_wait_time:.1f} seconds")

        sleep_time = min(interval, remaining)
        time.sleep(sleep_time)
        interval = min(interval * DEFAULT_MULTIPLIER, DEFAULT_MAX_INTERVAL)


def _parse_ocr_result(job_id: str, jsonl_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse OCR result into compatible format.

    Args:
        job_id: Job ID
        jsonl_data: JSONL data list

    Returns:
        Dict with job_id and pages list

    Raises:
        RuntimeError: If parsing fails
    """
    try:
        pages = []
        for line_obj in jsonl_data:
            result = line_obj["result"]
            for item in result["ocrResults"]:
                pages.append(
                    {
                        "pruned_result": item["prunedResult"],
                        "ocr_image_url": item.get("ocrImage"),
                    }
                )
        return {
            "job_id": job_id,
            "pages": pages,
        }
    except (KeyError, TypeError) as e:
        raise RuntimeError(f"Malformed OCR result payload: {e}") from e


def _parse_doc_parsing_result(job_id: str, jsonl_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse doc parsing result into compatible format.

    Args:
        job_id: Job ID
        jsonl_data: JSONL data list

    Returns:
        Dict with job_id and pages list

    Raises:
        RuntimeError: If parsing fails
    """
    try:
        pages = []
        for line_obj in jsonl_data:
            result = line_obj["result"]
            for item in result["layoutParsingResults"]:
                markdown = item["markdown"]
                pages.append(
                    {
                        "markdown_text": markdown["text"],
                        "markdown_images": markdown.get("images", {}),
                        "output_images": item.get("outputImages", {}),
                    }
                )
        return {
            "job_id": job_id,
            "pages": pages,
        }
    except (KeyError, TypeError) as e:
        raise RuntimeError(f"Malformed document parsing result payload: {e}") from e


def call_paddleocr_api(
    model: str,
    file_url: str | None,
    file_path: str | None,
    options: dict[str, Any],
    client_config: dict[str, Any],
    is_document_parsing: bool = False,
) -> dict[str, Any]:
    """Call PaddleOCR API using async job pattern.

    Args:
        model: Model name (e.g., "PP-OCRv5", "PP-StructureV3", "PaddleOCR-VL-1.6")
        file_url: URL of the file (if using URL input)
        file_path: Path to the file (if using file input)
        options: Optional payload parameters
        client_config: Client config from get_sdk_client()
        is_document_parsing: True for doc parsing, False for OCR

    Returns:
        Parsed result dict with job_id and pages

    Raises:
        RuntimeError: If API call fails
    """
    job_id = _submit_job(
        model, file_url, file_path, options, client_config["base_url"], client_config["headers"]
    )
    jsonl_data, status_data = _poll_job(
        job_id, client_config["base_url"], client_config["headers"]
    )

    if is_document_parsing:
        return _parse_doc_parsing_result(job_id, jsonl_data)
    else:
        return _parse_ocr_result(job_id, jsonl_data)