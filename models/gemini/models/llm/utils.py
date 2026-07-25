import threading
import time


class FileCache:
    """In-memory, thread-safe cache with lazy expiry-based eviction.

    Replaces the original disk-backed JSON implementation, which re-read and
    re-wrote the entire file on every exists()/get()/setex() call with no
    locking -- concurrent plugin-daemon workers could corrupt the file or
    lose updates, and every operation paid a full-file read/parse (or
    read/parse/serialize/write for setex()) cost.

    Note on persistence trade-off: this cache backs Gemini Files API
    uploads (see file_parts.GeminiFilePartFactory), which are free to
    re-upload and expire on Google's side after ~48h anyway. Losing the
    cache across a plugin-daemon restart only costs a re-upload of
    recently-used files, not correctness or data. The performance and
    concurrency-safety win of an in-memory cache outweighs keeping the
    disk-backed persistence.
    """

    _EVICT_AFTER_ENTRIES = 500
    _EVICT_MIN_INTERVAL_SECONDS = 600

    def __init__(self, cache_file="file_cache.json"):
        # Kept for backward-compatible signature; no longer used for storage.
        self.cache_file = cache_file
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._last_evict_at = time.time()

    def _maybe_evict_locked(self):
        """Purge expired entries — or the oldest entries if none are expired —
        once the cache has grown large enough and enough time has passed since
        the last purge. Must be called while holding self._lock.

        Without the ``while`` loop, a cache with >``_EVICT_AFTER_ENTRIES``
        entries that are all long-lived (none expired) would update
        ``_last_evict_at`` and continue growing unboundedly across ``setex``
        calls.
        """
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
            while len(self._cache) > self._EVICT_AFTER_ENTRIES:
                self._cache.pop(next(iter(self._cache)))
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
