"""Tests for session_manager.py utility module."""
import time
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.utils.session_manager import (
    SessionManager,
    cache_session,
    get_cached_session,
    get_session_status,
    invalidate_session_cache,
    list_active_sessions,
    update_session_status,
)


class TestSessionManager:
    """Test suite for SessionManager."""

    def test_lru_cache_set_and_get(self):
        mgr = SessionManager(max_lru_size=10)
        mgr.set_cached_result("sid1", "key1", {"value": 42})
        result = mgr.get_cached_result("sid1", "key1")
        assert result == {"value": 42}

    def test_lru_cache_miss(self):
        mgr = SessionManager(max_lru_size=10)
        result = mgr.get_cached_result("sid1", "nonexistent")
        assert result is None

    def test_lru_cache_eviction(self):
        mgr = SessionManager(max_lru_size=2)
        mgr.set_cached_result("sid", "k1", 1)
        mgr.set_cached_result("sid", "k2", 2)
        mgr.set_cached_result("sid", "k3", 3)
        # k1 should have been evicted
        assert mgr.get_cached_result("sid", "k1") is None
        assert mgr.get_cached_result("sid", "k3") == 3

    def test_cache_dataframe(self):
        mgr = SessionManager(max_lru_size=10)
        df = pd.DataFrame({"a": [1, 2, 3]})
        mgr.cache_dataframe("sid", "features", df)
        result = mgr.get_cached_dataframe("sid", "features")
        assert result is not None
        assert result.equals(df)

    def test_invalidate_cache(self):
        mgr = SessionManager(max_lru_size=10)
        mgr.set_cached_result("sid", "k1", 1)
        mgr.invalidate_cache("sid")
        assert mgr.get_cached_result("sid", "k1") is None

    def test_analysis_cache_key(self):
        mgr = SessionManager(max_lru_size=10)
        key = mgr.get_analysis_cache_key("alpha", {"metric": "shannon"})
        assert key.startswith("analysis:alpha:")

    def test_redis_not_available(self):
        with patch("app.utils.session_manager._get_redis_client", return_value=None):
            mgr = SessionManager(max_lru_size=10)
            mgr.set_cached_result("sid", "k1", 1)
            result = mgr.get_cached_result("sid", "k1")
            assert result == 1


class TestModuleFunctions:
    """Test module-level convenience functions."""

    def test_cache_session_and_get(self):
        cache_session("sid1", {"status": "active"}, ttl=60)
        result = get_cached_session("sid1")
        assert result["status"] == "active"

    def test_cache_session_expiration(self):
        cache_session("sid_exp", {"status": "active"}, ttl=0)
        time.sleep(0.01)
        result = get_cached_session("sid_exp")
        assert result is None

    def test_invalidate_session_cache(self):
        cache_session("sid2", {"status": "active"})
        invalidate_session_cache("sid2")
        assert get_cached_session("sid2") is None

    def test_get_session_status(self):
        cache_session("sid3", {"status": "processing"})
        assert get_session_status("sid3") == "processing"
        assert get_session_status("nonexistent") is None

    def test_update_session_status(self):
        cache_session("sid4", {"status": "created"})
        update_session_status("sid4", "completed")
        assert get_session_status("sid4") == "completed"

    def test_list_active_sessions(self):
        cache_session("sid_a", {"data": 1}, ttl=3600)
        cache_session("sid_b", {"data": 2}, ttl=3600)
        active = list_active_sessions()
        assert "sid_a" in active
        assert "sid_b" in active
