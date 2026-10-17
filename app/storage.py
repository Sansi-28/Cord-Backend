import os
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
COLLAGE_DIR = os.path.join(BASE_DIR, "collages")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")

def init_storage_directories():
    for directory in [UPLOAD_DIR, COLLAGE_DIR, GENERATED_DIR]:
        os.makedirs(directory, exist_ok=True)

def resolve_file_path(filename: str) -> Optional[str]:
    """Search for the file in upload, generated, and collage directories safely."""
    # Prevent directory traversal
    safe_filename = os.path.basename(filename)
    for directory in [UPLOAD_DIR, GENERATED_DIR, COLLAGE_DIR]:
        candidate = os.path.join(directory, safe_filename)
        if os.path.exists(candidate):
            return candidate
    return None
