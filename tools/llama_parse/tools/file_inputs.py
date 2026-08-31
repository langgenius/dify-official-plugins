from collections.abc import Callable
from typing import Any, TypeVar

import nest_asyncio

T = TypeVar("T")


def iter_files(files: Any) -> list[Any]:
    """Normalize the Dify ``files`` parameter to a non-empty list."""
    if files is None:
        raise ValueError("File is required")
    if isinstance(files, list):
        if not files:
            raise ValueError("File is required")
        return files
    return [files]


def file_name(file: Any) -> str:
    name = getattr(file, "filename", None) or getattr(file, "name", None)
    if not name:
        raise ValueError("Each file must have a filename with an extension")
    return str(name)


def file_bytes(file: Any) -> bytes:
    """Return file contents as ``bytes`` for LlamaParse.

    LlamaParse treats anything that is not ``bytes`` / a buffer / a path string
    as a type error (``file_path must be a string or a list of strings``).
    Dify File blobs can be ``bytearray`` or ``memoryview``; coerce those, and
    fail clearly when the payload is missing or nested.
    """
    blob = getattr(file, "blob", None)
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    elif isinstance(blob, bytearray):
        blob = bytes(blob)
    if isinstance(blob, bytes):
        if not blob:
            raise ValueError(f"File '{file_name(file)}' is empty")
        return blob
    raise ValueError(
        f"File '{file_name(file)}' is missing binary content. "
        "LlamaParse needs the file bytes on each File.blob."
    )


def call_sync(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Call a sync function that itself uses ``asyncio.run``.

    The Dify plugin daemon (gevent) may already be inside an event loop.
    LlamaParse ``load_data`` then raises
    ``asyncio.run() cannot be called from a running event loop``.
    """
    nest_asyncio.apply()
    return func(*args, **kwargs)
