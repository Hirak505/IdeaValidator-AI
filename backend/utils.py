import os
import tempfile
import uuid
from pathlib import Path
import time


UPLOAD_DIR = (Path(tempfile.gettempdir()) / "hackathon_judge_uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Set of allowed extensions for temp storage
ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".md"}


def get_temp_path(filename: str = "") -> str:
    """
    Generate a strictly isolated temporary file path.
    Does NOT use original filename to prevent PII leaks and path traversal attacks.
    """
    ext = ""
    if filename:
        raw_ext = Path(filename).suffix.lower()
        if raw_ext in ALLOWED_EXTENSIONS:
            ext = raw_ext
        else:
            ext = ".tmp"
    else:
        ext = ".tmp"

    # Generate a pure UUID-based filename
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    target_path = (UPLOAD_DIR / safe_filename).resolve()

    # Path traversal verification
    if not str(target_path).startswith(str(UPLOAD_DIR)):
        raise ValueError("Invalid temporary file path: Path traversal detected.")

    return str(target_path)


def delete_file(path: str) -> None:
    """
    Safely delete a temporary file.
    Ensures path stays within UPLOAD_DIR and handles Windows file lock retries.
    """
    if not path:
        return

    try:
        resolved = Path(path).resolve()
        # Security check: only delete files within UPLOAD_DIR
        if not str(resolved).startswith(str(UPLOAD_DIR)):
            return

        if resolved.is_file():
            # Attempt deletion with retries for Windows locks
            for attempt in range(3):
                try:
                    resolved.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.05)
                except Exception:
                    break
    except Exception:
        # Never leak exception or path in public errors
        pass


def cleanup_files(*paths: str) -> None:
    """Delete multiple temporary files safely."""
    for path in paths:
        if path:
            delete_file(path)
