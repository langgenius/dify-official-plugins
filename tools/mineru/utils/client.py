"""HTTP clients for the three MinerU APIs the plugin can talk to.

- ``CloudV4Client``: the MinerU official API (https://mineru.net/api/v4/...).
- ``LocalV1Client``: a self-hosted MinerU 4.x server (``mineru-kit api-server``, ``/v1/...``).
- ``LocalLegacyClient``: a self-hosted MinerU 1.x-3.x server (``mineru-api``, ``/file_parse``).

``detect_local_api`` decides between the two self-hosted flavours at call time, so a
customer can upgrade the MinerU server without touching the plugin configuration.
"""

import hashlib
import json
import logging
import mimetypes
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests

logger = logging.getLogger(__name__)

DEFAULT_CLOUD_BASE_URL = "https://mineru.net"
TOKEN_URL = "https://mineru.net/apiManage/token"

SERVER_TYPE_REMOTE = "remote"
SERVER_TYPE_LOCAL = "local"

API_CLOUD_V4 = "cloud_v4"
API_LOCAL_V1 = "local_v1"
API_LOCAL_LEGACY = "local_legacy"

# Unified job states exposed to workflows. Failed jobs raise instead of returning a state.
STATE_PENDING = "pending"
STATE_RUNNING = "running"
STATE_DONE = "done"

CLOUD_AUTH_ERROR_CODES = {"A0202", "A0211"}
CLOUD_QUOTA_ERROR_CODE = "-60018"
LEGACY_BACKENDS_NEED_SERVER_URL = {"vlm-sglang-client", "vlm-http-client", "hybrid-http-client"}
V1_EXTRA_FORMATS = {"html", "latex", "docx"}

_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
_SIMPLE_PAGE_RANGE_RE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


class MineruError(Exception):
    """A MinerU call failed; the message is meant to be shown to the user."""


class MineruAuthError(MineruError):
    """Credentials (token, API key or gateway header) were rejected."""


class MineruNetworkError(MineruError):
    """MinerU could not be reached; worth retrying while polling."""


@dataclass
class Credentials:
    server_type: str
    base_url: str
    token: str = ""
    gateway_header_name: str = ""
    gateway_header_value: str = ""

    @classmethod
    def from_mapping(cls, credentials: dict[str, Any]) -> "Credentials":
        server_type = (credentials.get("server_type") or SERVER_TYPE_LOCAL).strip()
        if server_type not in (SERVER_TYPE_REMOTE, SERVER_TYPE_LOCAL):
            raise MineruError(f"Unsupported server type: {server_type}")

        base_url = (credentials.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            if server_type == SERVER_TYPE_LOCAL:
                raise MineruError("Base URL is required for a self-hosted MinerU server, e.g. http://10.0.0.5:8000")
            base_url = DEFAULT_CLOUD_BASE_URL
        if not base_url.startswith(("http://", "https://")):
            raise MineruError(f"Base URL must start with http:// or https://, got: {base_url}")

        token = (credentials.get("token") or "").strip()
        if server_type == SERVER_TYPE_REMOTE and not token:
            raise MineruAuthError(f"An API token is required for the MinerU official API. Get one at {TOKEN_URL}")

        header_name = (credentials.get("gateway_header_name") or "").strip()
        header_value = (credentials.get("gateway_header_value") or "").strip()
        if bool(header_name) != bool(header_value):
            raise MineruError("Gateway header name and gateway header value must be filled in together.")
        if header_name and not _HEADER_NAME_RE.match(header_name):
            raise MineruError(f"Invalid gateway header name: {header_name}")

        return cls(
            server_type=server_type,
            base_url=base_url,
            token=token,
            gateway_header_name=header_name,
            gateway_header_value=header_value,
        )


@dataclass
class ParseOptions:
    """Union of the options of every MinerU API; each client reads the ones it understands."""

    # official API (cloud v4)
    model_version: str = "pipeline"
    enable_ocr: bool = False
    language: str = "auto"
    extra_formats: list[str] = field(default_factory=list)
    # official API and MinerU 2.x/3.x
    enable_formula: bool = True
    enable_table: bool = True
    # self-hosted, all versions
    parse_method: str = "auto"
    page_ranges: str = ""
    # MinerU 1.x-3.x
    backend: str = "pipeline"
    server_url: str = ""
    # MinerU 4.x
    tier: str = ""


@dataclass
class JobStatus:
    api: str
    state: str
    task_id: str = ""
    batch_id: str = ""
    progress: str = ""
    full_zip_url: str = ""
    # Filled once the job is done (local servers only; cloud results are fetched from full_zip_url)
    zip_bytes: bytes | None = None
    extra_files: dict[str, bytes] = field(default_factory=dict)
    legacy_response: dict[str, Any] | None = None
    legacy_version: str = ""


class MineruHttp:
    """Builds authenticated requests against ``credentials.base_url``."""

    def __init__(self, credentials: Credentials, timeout: float = 60):
        self.credentials = credentials
        self.timeout = timeout

    def url(self, path: str) -> str:
        return f"{self.credentials.base_url}/{path.lstrip('/')}"

    def auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.credentials.server_type == SERVER_TYPE_REMOTE:
            headers["source"] = "dify"
        if self.credentials.token:
            headers["Authorization"] = f"Bearer {self.credentials.token}"
        if self.credentials.server_type == SERVER_TYPE_LOCAL and self.credentials.gateway_header_name:
            headers[self.credentials.gateway_header_name] = self.credentials.gateway_header_value
        return headers

    def is_same_origin(self, url: str) -> bool:
        def origin(u: str) -> tuple[str, str, int]:
            parts = urlsplit(u)
            scheme = (parts.scheme or "").lower()
            return scheme, (parts.hostname or "").lower(), parts.port or (443 if scheme == "https" else 80)

        return origin(url) == origin(self.credentials.base_url)

    def request(self, method: str, path: str, *, timeout: float | None = None, **kwargs: Any) -> requests.Response:
        headers = {**self.auth_headers(), **kwargs.pop("headers", {})}
        try:
            return requests.request(
                method,
                self.url(path),
                headers=headers,
                timeout=timeout or self.timeout,
                allow_redirects=False,
                **kwargs,
            )
        except requests.Timeout as e:
            raise MineruNetworkError(f"Timed out waiting for MinerU at {self.credentials.base_url}: {e}") from e
        except requests.RequestException as e:
            raise MineruNetworkError(f"Cannot reach MinerU at {self.credentials.base_url}: {e}") from e

    def download(self, url: str, *, timeout: float | None = None) -> bytes:
        """GET a URL, following redirects manually so credentials never leave the MinerU origin."""
        current = url if url.startswith(("http://", "https://")) else self.url(url)
        for _ in range(5):
            headers = self.auth_headers() if self.is_same_origin(current) else {}
            try:
                response = requests.get(current, headers=headers, timeout=timeout or self.timeout, allow_redirects=False)
            except requests.RequestException as e:
                raise MineruNetworkError(f"Failed to download MinerU result: {e}") from e
            if response.is_redirect and response.headers.get("Location"):
                current = urljoin(current, response.headers["Location"])
                continue
            if not response.ok:
                raise MineruError(f"Failed to download MinerU result (HTTP {response.status_code}).")
            return response.content
        raise MineruError("Failed to download MinerU result: too many redirects.")


def _json_or_none(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _gateway_hint(credentials: Credentials) -> str:
    if credentials.gateway_header_name:
        return f"The gateway in front of MinerU rejected the request. Check the gateway header ({credentials.gateway_header_name})."
    return "The request was rejected before reaching MinerU. If a gateway is in front of MinerU, fill in the gateway header name and value in the plugin credentials."


def _mime_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


# ── MinerU official API (cloud v4) ────────────────────────────────────


class CloudV4Client:
    api = API_CLOUD_V4

    def __init__(self, http: MineruHttp):
        self.http = http

    def _data(self, response: requests.Response, action: str) -> dict[str, Any]:
        body = _json_or_none(response)
        code = str(body.get("code")) if isinstance(body, dict) else ""
        message = (body.get("msg") if isinstance(body, dict) else "") or response.text[:500]
        if response.status_code in (401, 403) or code in CLOUD_AUTH_ERROR_CODES:
            if code == "A0211":
                raise MineruAuthError(f"The MinerU API token has expired. Generate a new one at {TOKEN_URL} and update the plugin credentials.")
            raise MineruAuthError(f"The MinerU API token was rejected ({code or response.status_code}: {message}). Check it at {TOKEN_URL}.")
        if code == CLOUD_QUOTA_ERROR_CODE:
            raise MineruError(f"The MinerU daily parsing quota is used up ({message}).")
        if not response.ok or code != "0":
            raise MineruError(f"{action} failed (HTTP {response.status_code}, code {code or '-'}): {message}")
        return body.get("data") or {}

    @staticmethod
    def _common_options(options: ParseOptions) -> dict[str, Any]:
        return {
            "model_version": options.model_version or "pipeline",
            "enable_formula": options.enable_formula,
            "enable_table": options.enable_table,
            "language": options.language or "auto",
            "extra_formats": options.extra_formats,
        }

    def submit_file(self, filename: str, data: bytes, options: ParseOptions) -> JobStatus:
        entry: dict[str, Any] = {"name": filename, "is_ocr": options.enable_ocr}
        if options.page_ranges:
            entry["page_ranges"] = options.page_ranges
        response = self.http.request(
            "POST", "/api/v4/file-urls/batch", json={**self._common_options(options), "files": [entry]}
        )
        result = self._data(response, "Requesting an upload URL")
        batch_id, urls = result.get("batch_id"), result.get("file_urls") or []
        if not batch_id or not urls:
            raise MineruError(f"Unexpected response from MinerU when requesting an upload URL: {result}")
        # Pre-signed object-storage URL: no MinerU token and no Content-Type, or the signature breaks.
        try:
            upload = requests.put(urls[0], data=data, timeout=max(self.http.timeout, 300))
        except requests.RequestException as e:
            raise MineruError(f"Uploading the file to MinerU failed: {e}") from e
        if not upload.ok:
            raise MineruError(f"Uploading the file to MinerU failed (HTTP {upload.status_code}): {upload.text[:300]}")
        return JobStatus(api=self.api, state=STATE_PENDING, batch_id=batch_id)

    def submit_url(self, url: str, options: ParseOptions) -> JobStatus:
        body = {**self._common_options(options), "url": url, "is_ocr": options.enable_ocr}
        if options.page_ranges:
            body["page_ranges"] = options.page_ranges
        result = self._data(self.http.request("POST", "/api/v4/extract/task", json=body), "Creating the parse task")
        task_id = result.get("task_id")
        if not task_id:
            raise MineruError(f"Unexpected response from MinerU when creating the parse task: {result}")
        return JobStatus(api=self.api, state=STATE_PENDING, task_id=task_id)

    def _status(self, item: dict[str, Any], *, task_id: str = "", batch_id: str = "") -> JobStatus:
        state = item.get("state")
        if state == "failed":
            name = item.get("file_name") or task_id or batch_id
            raise MineruError(f"MinerU failed to parse {name}: {item.get('err_msg') or 'unknown error'}")
        progress = item.get("extract_progress") or {}
        status = JobStatus(api=self.api, state=STATE_PENDING, task_id=task_id, batch_id=batch_id)
        if progress.get("total_pages"):
            status.progress = f"{progress.get('extracted_pages', 0)}/{progress['total_pages']} pages"
        if state == "done":
            status.state = STATE_DONE
            status.full_zip_url = item.get("full_zip_url") or ""
            if not status.full_zip_url:
                raise MineruError("MinerU reported the task as done but returned no result URL.")
        elif state in ("running", "converting"):
            status.state = STATE_RUNNING
        return status

    def get_task(self, task_id: str) -> JobStatus:
        result = self._data(self.http.request("GET", f"/api/v4/extract/task/{task_id}"), "Querying the parse task")
        return self._status(result, task_id=task_id)

    def get_batch(self, batch_id: str) -> JobStatus:
        result = self._data(
            self.http.request("GET", f"/api/v4/extract-results/batch/{batch_id}"), "Querying the parse batch"
        )
        items = result.get("extract_result") or []
        if not items:
            return JobStatus(api=self.api, state=STATE_PENDING, batch_id=batch_id)
        return self._status(items[0], batch_id=batch_id)

    def fetch_zip(self, status: JobStatus) -> bytes:
        # The result zip lives on a public CDN; never send the token there.
        try:
            response = requests.get(status.full_zip_url, timeout=max(self.http.timeout, 300))
            response.raise_for_status()
        except requests.RequestException as e:
            raise MineruError(f"Failed to download the MinerU result zip: {e}") from e
        return response.content


# ── Self-hosted MinerU 4.x (/v1) ──────────────────────────────────────


class LocalV1Client:
    api = API_LOCAL_V1

    def __init__(self, http: MineruHttp):
        self.http = http

    def _json(self, response: requests.Response, action: str) -> dict[str, Any]:
        body = _json_or_none(response)
        error = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else None
        if response.ok and isinstance(body, dict):
            return body
        code = (error or {}).get("code") or ""
        message = (error or {}).get("message") or response.text[:500]
        if response.status_code in (401, 403) and error is None:
            raise MineruAuthError(_gateway_hint(self.http.credentials))
        if response.status_code == 401:
            raise MineruAuthError("The MinerU server requires an API key (it was started with --api-key). Fill in the API Token in the plugin credentials.")
        if code == "unsupported_output_format":
            raise MineruError(
                f"This MinerU server cannot export the requested extra formats ({message}). "
                "Self-hosted MinerU 4.x only returns Markdown, JSON and images; leave Extra export formats empty."
            )
        if code == "feature_requires_api_key":
            raise MineruError("Exporting html, latex or docx requires the MinerU server to be started with --api-key and the key filled in as the API Token.")
        if code == "quality_tier_unavailable":
            raise MineruError(f"The requested parsing tier is not available on this MinerU server: {message}")
        if response.status_code == 503:
            raise MineruError(f"The MinerU server is not ready or is busy: {message}")
        raise MineruError(f"{action} failed (HTTP {response.status_code}{', ' + code if code else ''}): {message}")

    def _upload(self, filename: str, data: bytes) -> str:
        sha256 = hashlib.sha256(data).hexdigest()
        created = self._json(
            self.http.request(
                "POST",
                "/v1/uploads",
                json={
                    "filename": filename,
                    "bytes": len(data),
                    "mime_type": _mime_type(filename),
                    "purpose": "parse",
                    "sha256sum": sha256,
                },
            ),
            "Creating the upload",
        )
        if created.get("status") == "completed" and (created.get("file") or {}).get("id"):
            return created["file"]["id"]  # the server already has these bytes

        upload_id = created.get("id")
        upload_url = created.get("upload_url")
        if not upload_id or not upload_url:
            raise MineruError(f"Unexpected response from MinerU when creating the upload: {created}")
        local_path = f"/v1/uploads/{upload_id}/content"
        upload_headers = {"Content-Type": "application/octet-stream", **(created.get("upload_headers") or {})}
        method = created.get("upload_method") or "PUT"
        if urlsplit(upload_url).path.endswith(local_path):
            # Same server: go through the configured base URL so gateways and path prefixes keep working.
            response = self.http.request(method, local_path, data=data, headers=upload_headers, timeout=max(self.http.timeout, 300))
        else:
            target = urljoin(self.http.url("/"), upload_url)
            headers = {**(self.http.auth_headers() if self.http.is_same_origin(target) else {}), **upload_headers}
            try:
                response = requests.request(method, target, data=data, headers=headers, timeout=max(self.http.timeout, 300))
            except requests.RequestException as e:
                raise MineruError(f"Uploading the file to MinerU failed: {e}") from e
        if not response.ok:
            self._json(response, "Uploading the file")

        completed = self._json(
            self.http.request("POST", f"/v1/uploads/{upload_id}/complete", json={"sha256sum": sha256}),
            "Completing the upload",
        )
        file_id = (completed.get("file") or {}).get("id")
        if not file_id:
            raise MineruError(f"Unexpected response from MinerU when completing the upload: {completed}")
        return file_id

    def _create_job(self, source: dict[str, Any], options: ParseOptions) -> JobStatus:
        entry: dict[str, Any] = {"source": source}
        if options.page_ranges:
            entry["page_range"] = options.page_ranges
        body: dict[str, Any] = {
            "files": [entry],
            "ocr_mode": options.parse_method if options.parse_method in ("auto", "txt", "ocr") else "auto",
            "output_formats": ["zip", *[f for f in options.extra_formats if f in V1_EXTRA_FORMATS]],
        }
        if options.tier and options.tier != "auto":
            body["tier"] = options.tier
        job = self._json(self.http.request("POST", "/v1/parse/jobs", json=body), "Creating the parse job")
        job_id = job.get("job_id")
        if not job_id:
            raise MineruError(f"Unexpected response from MinerU when creating the parse job: {job}")
        return JobStatus(api=self.api, state=STATE_PENDING, task_id=job_id)

    def submit_file(self, filename: str, data: bytes, options: ParseOptions) -> JobStatus:
        return self._create_job({"type": "file_id", "file_id": self._upload(filename, data)}, options)

    def submit_url(self, url: str, options: ParseOptions) -> JobStatus:
        return self._create_job({"type": "url", "url": url}, options)

    def get_job(self, job_id: str) -> JobStatus:
        response = self.http.request("GET", f"/v1/parse/jobs/{job_id}")
        if response.status_code == 404:
            raise MineruError(f"Parse job {job_id} was not found on this MinerU server (job ids do not survive a server restart).")
        job = self._json(response, "Querying the parse job")
        status = JobStatus(api=self.api, state=STATE_PENDING, task_id=job_id)
        files = job.get("files") or []
        progress = job.get("progress") or {}
        if progress.get("total"):
            status.progress = f"{progress.get('completed', 0)}/{progress['total']} files"

        job_state = job.get("status")
        if job_state in ("failed", "canceled") or (job_state == "partial" and not any(f.get("status") == "completed" for f in files)):
            errors = "; ".join(
                f"{f.get('name')}: {(f.get('error') or {}).get('message') or f.get('status')}" for f in files
            )
            raise MineruError(f"MinerU parse job {job_id} {job_state}: {errors or 'no details'}")
        if job_state == "running":
            status.state = STATE_RUNNING
        if job_state not in ("completed", "partial"):
            return status

        done = next((f for f in files if f.get("status") == "completed"), None)
        outputs = (done or {}).get("output_files") or {}
        if not outputs.get("zip"):
            raise MineruError(f"MinerU parse job {job_id} finished without a zip result.")
        status.zip_bytes = self.http.download(f"/v1/files/{outputs['zip']['file_id']}/content", timeout=max(self.http.timeout, 300))
        for fmt in V1_EXTRA_FORMATS:
            if outputs.get(fmt):
                status.extra_files[fmt] = self.http.download(f"/v1/files/{outputs[fmt]['file_id']}/content")
        status.state = STATE_DONE
        return status


# ── Self-hosted MinerU 1.x-3.x (/file_parse) ──────────────────────────


def legacy_page_ids(page_ranges: str) -> tuple[int, int] | None:
    """Convert a 1-based "3" or "3-10" range into /file_parse's 0-based start/end page ids."""
    if not page_ranges.strip():
        return None
    match = _SIMPLE_PAGE_RANGE_RE.match(page_ranges)
    if not match:
        raise MineruError(
            "MinerU 2.x/3.x servers only support a single continuous page range such as 3 or 3-10; "
            f"got: {page_ranges}"
        )
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if start < 1 or end < start:
        raise MineruError(f"Invalid page range: {page_ranges}")
    return start - 1, end - 1


class LocalLegacyClient:
    api = API_LOCAL_LEGACY

    def __init__(self, http: MineruHttp):
        self.http = http

    def _check(self, response: requests.Response) -> None:
        if response.status_code in (401, 403):
            raise MineruAuthError(_gateway_hint(self.http.credentials))
        if response.status_code == 503:
            raise MineruError("The MinerU server is busy (too many concurrent requests). Try again later.")
        if not response.ok:
            raise MineruError(f"MinerU failed to parse the file (HTTP {response.status_code}): {response.text[:500]}")

    @staticmethod
    def _is_v1_server(response: requests.Response) -> bool:
        """MinerU 1.x expects a single ``file`` field and answers 422 to the 2.x request."""
        body = _json_or_none(response)
        if response.status_code != 422 or not isinstance(body, dict) or not isinstance(body.get("detail"), list):
            return False
        return any(
            item.get("type") == "missing" and list(item.get("loc") or [])[:2] == ["body", "file"]
            for item in body["detail"]
        )

    def parse_file(self, filename: str, data: bytes, options: ParseOptions, timeout: float) -> JobStatus:
        if options.backend in LEGACY_BACKENDS_NEED_SERVER_URL and not options.server_url:
            raise MineruError(f"Backend {options.backend} requires the server url parameter.")
        language = (options.language or "").strip()
        form: dict[str, Any] = {
            "parse_method": options.parse_method or "auto",
            "return_md": True,
            "return_model_output": False,
            "return_content_list": True,
            "lang_list": [language] if language and language != "auto" else ["ch"],
            "return_images": True,
            "backend": options.backend or "pipeline",
            "formula_enable": options.enable_formula,
            "table_enable": options.enable_table,
            "return_middle_json": False,
        }
        if options.server_url:
            form["server_url"] = options.server_url
        page_ids = legacy_page_ids(options.page_ranges)
        if page_ids:
            form["start_page_id"], form["end_page_id"] = page_ids

        response = self.http.request(
            "POST", "/file_parse", data=form, files=[("files", (filename, data))], timeout=timeout
        )
        if self._is_v1_server(response):
            return self._parse_file_v1(filename, data, options, timeout)
        self._check(response)
        return JobStatus(api=self.api, state=STATE_DONE, legacy_response=response.json(), legacy_version="v2")

    def _parse_file_v1(self, filename: str, data: bytes, options: ParseOptions, timeout: float) -> JobStatus:
        params = {
            "parse_method": options.parse_method or "auto",
            "return_layout": False,
            "return_info": False,
            "return_content_list": True,
            "return_images": True,
        }
        response = self.http.request(
            "POST", "/file_parse", params=params, files={"file": (filename, data)}, timeout=timeout
        )
        self._check(response)
        return JobStatus(api=self.api, state=STATE_DONE, legacy_response=response.json(), legacy_version="v1")


# ── detection and credential validation ───────────────────────────────


def detect_local_api(http: MineruHttp) -> str:
    """Return API_LOCAL_V1 for MinerU 4.x servers and API_LOCAL_LEGACY otherwise."""
    response = http.request("GET", "/v1/health", timeout=15)
    body = _json_or_none(response)
    if response.status_code == 200 and isinstance(body, dict) and "version" in body and "features" in body:
        return API_LOCAL_V1
    if response.status_code == 503 and isinstance(body, dict) and isinstance(body.get("error"), dict):
        return API_LOCAL_V1  # 4.x server that is still loading models
    if response.status_code in (401, 403):
        # /v1/health is public on MinerU itself, so this came from a gateway.
        raise MineruAuthError(_gateway_hint(http.credentials))
    return API_LOCAL_LEGACY


def make_client(credentials: Credentials, timeout: float = 60) -> CloudV4Client | LocalV1Client | LocalLegacyClient:
    http = MineruHttp(credentials, timeout=timeout)
    if credentials.server_type == SERVER_TYPE_REMOTE:
        return CloudV4Client(http)
    if detect_local_api(http) == API_LOCAL_V1:
        return LocalV1Client(http)
    return LocalLegacyClient(http)


def validate_credentials(credentials: Credentials) -> None:
    http = MineruHttp(credentials, timeout=15)
    if credentials.server_type == SERVER_TYPE_REMOTE:
        # Read-only probe: an unknown task id returns a "not found" business code when the token is valid.
        response = http.request("GET", "/api/v4/extract/task/00000000-0000-0000-0000-000000000000")
        body = _json_or_none(response)
        code = str(body.get("code")) if isinstance(body, dict) else ""
        if response.status_code in (401, 403) or code in CLOUD_AUTH_ERROR_CODES:
            CloudV4Client(http)._data(response, "Validating the token")
        if not isinstance(body, dict) or "code" not in body:
            raise MineruError(
                f"Unexpected response from {credentials.base_url} (HTTP {response.status_code}). "
                f"Check the Base URL; the official API is {DEFAULT_CLOUD_BASE_URL}."
            )
        return

    if detect_local_api(http) == API_LOCAL_V1:
        # /v1/health is public; /v1/files is protected when the server runs with --api-key.
        LocalV1Client(http)._json(http.request("GET", "/v1/files", params={"limit": 1}), "Validating the API key")
        return

    rejected = False
    for path in ("/openapi.json", "/docs", "/health"):
        response = http.request("GET", path)
        if response.status_code == 200:
            return
        rejected = rejected or response.status_code in (401, 403)
    if rejected:
        raise MineruAuthError(_gateway_hint(credentials))
    raise MineruError(f"{credentials.base_url} does not look like a MinerU server. Check the Base URL.")


def parse_extra_formats(value: Any) -> list[str]:
    """Accept '["docx","html"]', 'docx,html' or a list."""
    if not value:
        return []
    if isinstance(value, list):
        items = value
    else:
        text = str(value).strip()
        try:
            items = json.loads(text) if text.startswith("[") else text.split(",")
        except json.JSONDecodeError as e:
            raise MineruError(f'Extra export formats must look like ["docx","html"]; got: {text}') from e
    formats = [str(item).strip().lower() for item in items if str(item).strip()]
    unknown = [f for f in formats if f not in V1_EXTRA_FORMATS]
    if unknown:
        raise MineruError(f"Unsupported extra export formats: {unknown}. Supported: docx, html, latex.")
    return formats
