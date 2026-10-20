import os
import tempfile
import uuid
from pathlib import Path
import time


UPLOAD_DIR = (Path(tempfile.gettempdir()) / "hackathon_judge_uploads").resolve()

# Ensure UPLOAD_DIR cannot be hijacked via a symlink in shared temp spaces
if UPLOAD_DIR.is_symlink():
    raise RuntimeError("Insecure temporary directory: UPLOAD_DIR is a symbolic link.")

UPLOAD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
try:
    os.chmod(UPLOAD_DIR, 0o700)
except OSError:
    pass

# Set of allowed extensions for temp storage (legacy .ppt is not supported)
ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".md"}


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
    Ensures path stays within UPLOAD_DIR, avoids following symlinks,
    and handles Windows file lock retries.
    """
    if not path:
        return

    try:
        raw_path = Path(path)
        # Avoid following symlinks outside UPLOAD_DIR
        if raw_path.is_symlink():
            if str(raw_path.resolve()).startswith(str(UPLOAD_DIR)):
                raw_path.unlink(missing_ok=True)
            return

        resolved = raw_path.resolve()
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


def cleanup_stale_temp_files(max_age_seconds: int = 3600) -> int:
    """
    Delete orphaned temporary files older than max_age_seconds.
    Safe for periodic maintenance and app startup.
    Avoids deleting active uploads or following symbolic links.
    Returns the count of deleted files.
    """
    removed_count = 0
    now = time.time()
    try:
        if UPLOAD_DIR.is_dir() and not UPLOAD_DIR.is_symlink():
            for child in UPLOAD_DIR.iterdir():
                try:
                    # Clean symlinks without following them outside UPLOAD_DIR
                    if child.is_symlink():
                        child.unlink(missing_ok=True)
                        removed_count += 1
                        continue

                    if child.is_file():
                        mtime = child.stat().st_mtime
                        if now - mtime > max_age_seconds:
                            child.unlink(missing_ok=True)
                            removed_count += 1
                except OSError:
                    pass
    except OSError:
        pass
    return removed_count
