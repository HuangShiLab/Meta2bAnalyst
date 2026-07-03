"""
Meta2bAnalyst - Session Manager Utility
Handles session lifecycle, caching (LRU + Redis), and metadata.
"""
import hashlib
import json
import logging
import pickle
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory session cache (LRU-style, not persistent)
_session_cache: Dict[str, Dict[str, Any]] = {}
_result_cache: Dict[str, Dict[str, Any]] = {}

# Redis cache client (lazy initialization)
_redis_client = None


def _get_redis_client():
    """Get or create Redis client if available."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    
    try:
        import redis
        r = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=5,
            decode_responses=False,
        )
        r.ping()
        _redis_client = r
        logger.info("Redis cache connected")
        return _redis_client
    except Exception as e:
        logger.debug(f"Redis not available for caching: {e}")
        _redis_client = False
        return None


def _make_cache_key(session_id: str, params: Dict[str, Any]) -> str:
    """Generate a deterministic cache key from session ID and parameters."""
    param_str = json.dumps(params, sort_keys=True, default=str)
    return f"meta2b:{session_id}:{hashlib.md5(param_str.encode()).hexdigest()}"


class SessionManager:
    """Session manager with LRU and Redis caching support."""

    def __init__(self, max_lru_size: int = 100):
        self._lru_cache: Dict[str, Any] = {}
        self._lru_access: Dict[str, float] = {}
        self.max_lru_size = max_lru_size

    def _evict_lru(self) -> None:
        """Evict least recently used items when cache exceeds max size."""
        if len(self._lru_cache) <= self.max_lru_size:
            return
        
        sorted_keys = sorted(self._lru_access.items(), key=lambda x: x[1])
        to_evict = sorted_keys[:len(sorted_keys) - self.max_lru_size]
        for key, _ in to_evict:
            self._lru_cache.pop(key, None)
            self._lru_access.pop(key, None)
            logger.debug(f"LRU evicted: {key}")

    def get_cached_result(self, session_id: str, cache_key: str) -> Optional[Any]:
        """Get result from cache (Redis first, then LRU)."""
        full_key = f"{session_id}:{cache_key}"
        
        # Try Redis first
        redis_client = _get_redis_client()
        if redis_client:
            try:
                data = redis_client.get(full_key)
                if data:
                    result = pickle.loads(data)
                    logger.debug(f"Redis cache hit: {full_key}")
                    return result
            except Exception as e:
                logger.warning(f"Redis cache read failed: {e}")
        
        # Try LRU cache
        if full_key in self._lru_cache:
            self._lru_access[full_key] = time.time()
            logger.debug(f"LRU cache hit: {full_key}")
            return self._lru_cache[full_key]
        
        return None

    def set_cached_result(self, session_id: str, cache_key: str, result: Any, ttl: int = 3600) -> None:
        """Cache result in Redis and LRU."""
        full_key = f"{session_id}:{cache_key}"
        
        # Store in Redis
        redis_client = _get_redis_client()
        if redis_client:
            try:
                redis_client.setex(full_key, ttl, pickle.dumps(result))
                logger.debug(f"Redis cache set: {full_key} (TTL={ttl}s)")
            except Exception as e:
                logger.warning(f"Redis cache write failed: {e}")
        
        # Store in LRU
        self._lru_cache[full_key] = result
        self._lru_access[full_key] = time.time()
        self._evict_lru()

    def invalidate_cache(self, session_id: str) -> None:
        """Clear all cached results for a session."""
        prefix = f"{session_id}:"
        
        # Clear Redis
        redis_client = _get_redis_client()
        if redis_client:
            try:
                keys = redis_client.keys(f"{prefix}*")
                if keys:
                    redis_client.delete(*keys)
                    logger.info(f"Invalidated {len(keys)} Redis keys for session {session_id}")
            except Exception as e:
                logger.warning(f"Redis cache invalidation failed: {e}")
        
        # Clear LRU
        keys_to_remove = [k for k in self._lru_cache.keys() if k.startswith(prefix)]
        for k in keys_to_remove:
            self._lru_cache.pop(k, None)
            self._lru_access.pop(k, None)
        
        logger.info(f"Invalidated {len(keys_to_remove)} LRU entries for session {session_id}")

    def cache_dataframe(self, session_id: str, data_type: str, df: Any, ttl: int = 7200) -> None:
        """Cache a preprocessed DataFrame (filtered/normalized)."""
        cache_key = f"data:{data_type}"
        self.set_cached_result(session_id, cache_key, df, ttl=ttl)

    def get_cached_dataframe(self, session_id: str, data_type: str) -> Optional[Any]:
        """Retrieve cached preprocessed DataFrame."""
        cache_key = f"data:{data_type}"
        return self.get_cached_result(session_id, cache_key)

    def get_analysis_cache_key(self, analysis_type: str, parameters: Dict[str, Any]) -> str:
        """Generate cache key for analysis results based on parameters."""
        return f"analysis:{analysis_type}:{_make_cache_key('', parameters)}"


# Module-level convenience functions (backward compatible)

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
