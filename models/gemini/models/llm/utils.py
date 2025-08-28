import os
import json
import pathlib
import time
import tempfile


class FileCache:
    def __init__(self, cache_file="file_cache.json"):
        dir = os.path.dirname(cache_file)
        try:
            # try to check if the cache file is writable
            with tempfile.TemporaryDirectory(dir=dir):
                self.cache_file = cache_file
        except Exception:
            self.cache_file = str(pathlib.Path(tempfile.gettempdir()) / cache_file)

        self._ensure_cache_file()

    def _ensure_cache_file(self):
        if not os.path.exists(self.cache_file):
            with open(self.cache_file, "w") as f:
                json.dump({}, f)

    def _load_cache(self):
        try:
            with open(self.cache_file, "r") as f:
                cache = json.load(f)
            return cache
        except Exception:
            return {}

    def _save_cache(self, cache):
        cleaned_cache = {k: v for k, v in cache.items() if v.get("expires_at", 0) > time.time()}
        with open(self.cache_file, "w") as f:
            json.dump(cleaned_cache, f)

    def exists(self, key):
        cache = self._load_cache()
        return key in cache and cache[key].get("expires_at", 0) > time.time()

    def get(self, key):
        cache = self._load_cache()
        if key in cache and cache[key].get("expires_at", 0) > time.time():
            return cache[key]["value"]
        return None

    def setex(self, key, expires_in_seconds, value):
        cache = self._load_cache()
        cache[key] = {"value": value, "expires_at": time.time() + expires_in_seconds}
        self._save_cache(cache)


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
