import threading
import time


class FileCache:
    """In-memory, thread-safe cache with lazy expiry-based eviction.

    Replaces the original disk-backed JSON implementation, which re-read and
    re-wrote the whole file on every exists/get/setex call with no locking
    (concurrent workers could lose updates or corrupt the file) and paid
    blocking disk I/O on every multimodal content check.

    Intentional trade-off: entries no longer survive a process restart, so
    identical files may be re-uploaded to the Files API after a restart.
    The upload is free and only costs a little latency, so in-memory storage
    is the safer, faster choice.
    """

    _EVICT_AFTER_ENTRIES = 500
    _EVICT_MIN_INTERVAL_SECONDS = 600

    def __init__(self, cache_file="file_cache.json"):
        # kept for backward-compatible signature; no longer used for storage
        self.cache_file = cache_file
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._last_evict_at = time.time()

    def _maybe_evict_locked(self):
        now = time.time()
        if (
            len(self._cache) > self._EVICT_AFTER_ENTRIES
            and now - self._last_evict_at > self._EVICT_MIN_INTERVAL_SECONDS
        ):
            expired = [
                k for k, v in self._cache.items() if v.get("expires_at", 0) <= now
            ]
            for k in expired:
                del self._cache[k]
            self._last_evict_at = now

    def exists(self, key):
        with self._lock:
            entry = self._cache.get(key)
            return entry is not None and entry.get("expires_at", 0) > time.time()

    def get(self, key):
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and entry.get("expires_at", 0) > time.time():
                return entry["value"]
            return None

    def setex(self, key, expires_in_seconds, value):
        with self._lock:
            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + expires_in_seconds,
            }
            self._maybe_evict_locked()


# Gemini API File Type Support Constants
# Based on official Gemini API documentation for multimodal models

# Supported image MIME types

# Unsupported document MIME types (blacklist for documents)
# Microsoft Office formats are not supported by Gemini API
UNSUPPORTED_DOCUMENT_TYPES = {
    # Microsoft Word
    "application/msword",  # .doc
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    # Microsoft Excel
    "application/vnd.ms-excel",  # .xls
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    # Microsoft PowerPoint
    "application/vnd.ms-powerpoint",  # .ppt
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
    # OpenDocument formats
    "application/vnd.oasis.opendocument.text",  # .odt
    "application/vnd.oasis.opendocument.spreadsheet",  # .ods
    "application/vnd.oasis.opendocument.presentation",  # .odp
}

# File extensions that are not supported (for additional validation)
UNSUPPORTED_EXTENSIONS = {
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "odt",
    "ods",
    "odp",
    "rtf",
    "wps",
    "epub",
    "mdx",
    "markdown",
}
