"""Tests for file_storage.py utility module."""
import os
from pathlib import Path

import pytest

from app.config import settings
from app.utils.file_storage import (
    cleanup_old_sessions,
    delete_session_files,
    get_file_size,
    get_session_exports_dir,
    get_session_results_dir,
    get_session_upload_dir,
    list_session_files,
    sanitize_filename,
    save_file,
)


class TestFileStorage:
    """Test suite for file storage utilities."""

    def test_get_session_upload_dir(self):
        session_dir = get_session_upload_dir("test-session")
        assert session_dir.exists()
        assert session_dir.name == "test-session"

    def test_get_session_results_dir(self):
        results_dir = get_session_results_dir("test-session")
        assert results_dir.exists()
        assert results_dir.name == "results"

    def test_get_session_exports_dir(self):
        exports_dir = get_session_exports_dir("test-session")
        assert exports_dir.exists()
        assert exports_dir.name == "exports"

    def test_save_file(self):
        content = b"test content"
        path = save_file("test-session", "test.txt", content)
        assert path.exists()
        assert path.read_bytes() == content

    def test_save_file_with_subdirectory(self):
        content = b"sub content"
        path = save_file("test-session", "sub.txt", content, subdirectory="sub")
        assert path.exists()
        assert path.parent.name == "sub"

    def test_list_session_files(self):
        save_file("test-session", "a.txt", b"a")
        save_file("test-session", "b.txt", b"b", subdirectory="sub")
        files = list_session_files("test-session")
        assert len(files) >= 2

    def test_list_session_files_nonexistent(self):
        files = list_session_files("nonexistent-session-12345")
        assert files == []

    def test_delete_session_files(self):
        save_file("test-del", "file.txt", b"data")
        assert delete_session_files("test-del") is True
        # Directory may or may not exist after deletion
        assert not (Path(settings.UPLOAD_DIR) / "test-del" / "file.txt").exists()

    def test_delete_session_files_nonexistent(self):
        assert delete_session_files("nonexistent-session-12345") is True

    def test_get_file_size(self):
        path = save_file("test-size", "file.txt", b"12345")
        assert get_file_size(path) == 5

    def test_get_file_size_nonexistent(self):
        assert get_file_size(Path("/nonexistent/path")) == 0

    def test_sanitize_filename(self):
        assert sanitize_filename("<bad>:name*.txt") == "_bad__name_.txt"

    def test_cleanup_old_sessions_no_upload_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            import app.config
            orig = app.config.settings.UPLOAD_DIR
            app.config.settings.UPLOAD_DIR = tmpdir + "/nonexistent"
            count = cleanup_old_sessions(max_age_days=0)
            assert count == 0
            app.config.settings.UPLOAD_DIR = orig
