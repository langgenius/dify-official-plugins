from pathlib import Path

PROJECT_DIR = Path(__file__).parent
CACHE_DIR = PROJECT_DIR.joinpath(".cache")
UPLOAD_DIR = CACHE_DIR / "uploads"

# Initialize disk cache
DISK_CACHE_DIR = CACHE_DIR / "artifact_cache"
ARTIFACT_FILES_DIR = CACHE_DIR / "artifact_files"
