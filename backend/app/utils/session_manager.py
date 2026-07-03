"""
Meta2bAnalyst - Session Manager Utility
Handles session lifecycle, caching, and metadata.
"""
import logging
import time
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory session cache (for fast lookups, not persistent)
_session_cache: Dict[str, Dict[str, Any]] = {}


def cache_session(session_id: str, data: Dict[str, Any], ttl: int = 3600) -> None:
    """
    Cache session data in memory.

    Args:
        session_id: Session ID
        data: Data to cache
        ttl: Time-to-live in seconds
    """
    _session_cache[session_id] = {
        "data": data,
        "expires": time.time() + ttl,
    }
    logger.debug(f"Cached session {session_id} (TTL: {ttl}s)")


def get_cached_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get cached session data if not expired."""
    if session_id not in _session_cache:
        return None
    
    cache_entry = _session_cache[session_id]
    if time.time() > cache_entry["expires"]:
        del _session_cache[session_id]
        return None
    
    return cache_entry["data"]


def invalidate_session_cache(session_id: str) -> None:
    """Remove session from cache."""
    if session_id in _session_cache:
        del _session_cache[session_id]
        logger.debug(f"Invalidated cache for session {session_id}")


def get_session_status(session_id: str) -> Optional[str]:
    """Get cached session status."""
    cached = get_cached_session(session_id)
    if cached and "status" in cached:
        return cached["status"]
    return None


def update_session_status(session_id: str, status: str) -> None:
    """Update cached session status."""
    cached = get_cached_session(session_id) or {}
    cached["status"] = status
    cache_session(session_id, cached)


def list_active_sessions() -> Dict[str, Dict[str, Any]]:
    """List all active (non-expired) cached sessions."""
    now = time.time()
    active = {}
    expired = []
    
    for session_id, entry in _session_cache.items():
        if entry["expires"] > now:
            active[session_id] = entry["data"]
        else:
            expired.append(session_id)
    
    # Clean up expired entries
    for session_id in expired:
        del _session_cache[session_id]
    
    return active
