"""
Meta2bAnalyst - File Storage Utility
Handles file operations, storage paths, and cleanup.
"""
import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


def get_session_upload_dir(session_id: str) -> Path:
    """Get the upload directory for a session."""
    session_dir = Path(settings.UPLOAD_DIR) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def get_session_results_dir(session_id: str) -> Path:
    """Get the results directory for a session."""
    results_dir = Path(settings.UPLOAD_DIR) / session_id / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def get_session_exports_dir(session_id: str) -> Path:
    """Get the exports directory for a session."""
    exports_dir = Path(settings.UPLOAD_DIR) / session_id / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    return exports_dir


def save_file(
    session_id: str,
    filename: str,
    content: bytes,
    subdirectory: Optional[str] = None,
) -> Path:
    """
    Save a file to the session directory.

    Args:
        session_id: Session ID
        filename: File name
        content: File content as bytes
        subdirectory: Optional subdirectory within session directory

    Returns:
        Path to saved file
    """
    session_dir = get_session_upload_dir(session_id)
    if subdirectory:
        target_dir = session_dir / subdirectory
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = session_dir
    
    file_path = target_dir / filename
    with open(file_path, "wb") as f:
        f.write(content)
    
    logger.info(f"Saved file {filename} to {file_path}")
    return file_path


def list_session_files(session_id: str) -> List[Path]:
    """List all files in a session directory."""
    session_dir = get_session_upload_dir(session_id)
    if not session_dir.exists():
        return []
    return [f for f in session_dir.rglob("*") if f.is_file()]


def delete_session_files(session_id: str) -> bool:
    """Delete all files associated with a session."""
    session_dir = Path(settings.UPLOAD_DIR) / session_id
    if session_dir.exists():
        try:
            shutil.rmtree(session_dir)
            logger.info(f"Deleted session directory: {session_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete session directory {session_dir}: {e}")
            return False
    return True


def get_file_size(file_path: Path) -> int:
    """Get file size in bytes."""
    if file_path.exists():
        return file_path.stat().st_size
    return 0


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe storage."""
    # Remove or replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    return filename.strip()


def cleanup_old_sessions(max_age_days: int = 30) -> int:
    """
    Clean up session directories older than max_age_days.

    Returns:
        Number of directories cleaned up
    """
    import time
    cutoff = time.time() - (max_age_days * 24 * 60 * 60)
    cleaned = 0
    
    upload_dir = Path(settings.UPLOAD_DIR)
    if not upload_dir.exists():
        return 0
    
    for session_dir in upload_dir.iterdir():
        if session_dir.is_dir():
            try:
                mtime = session_dir.stat().st_mtime
                if mtime < cutoff:
                    shutil.rmtree(session_dir)
                    cleaned += 1
                    logger.info(f"Cleaned up old session directory: {session_dir}")
            except Exception as e:
                logger.error(f"Failed to clean up {session_dir}: {e}")
    
    return cleaned
