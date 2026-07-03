"""
Meta2bAnalyst - Celery Application Configuration
Supports Redis (production) and SQLite (development fallback) as broker.
"""
import logging
import os

from celery import Celery

logger = logging.getLogger(__name__)

# ─────────────────────────────── Broker detection

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)


def _check_redis_available(url: str) -> bool:
    """Check if Redis is reachable."""
    try:
        import redis
        r = redis.from_url(url, socket_connect_timeout=2)
        r.ping()
        return True
    except Exception as e:
        logger.warning(f"Redis not available at {url}: {e}")
        return False


# Auto-detect broker: prefer Redis, fallback to SQLite
if _check_redis_available(CELERY_BROKER_URL):
    broker = CELERY_BROKER_URL
    backend = CELERY_RESULT_BACKEND
    broker_type = "redis"
    logger.info(f"Celery using Redis broker: {broker}")
else:
    # SQLite fallback for development
    broker = "sqlalchemy+sqlite:///./celerydb.sqlite"
    backend = "db+sqlite:///./celerydb.sqlite"
    broker_type = "sqlite"
    logger.info(f"Celery using SQLite broker (Redis unavailable): {broker}")

    # Ensure the SQLite database file directory exists
    os.makedirs(os.path.dirname("./celerydb.sqlite") or ".", exist_ok=True)


celery_app = Celery(
    "meta2banalyst",
    broker=broker,
    backend=backend,
    include=[
        "app.tasks.analysis_tasks",
    ],
)

# ─────────────────────────────── Task configuration

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task behavior
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard timeout
    task_soft_time_limit=3000,  # 50 minutes soft timeout
    worker_prefetch_multiplier=1,  # Fair task distribution
    worker_concurrency=2,  # Number of worker processes
    
    # Result backend settings
    result_expires=3600 * 24,  # Results expire after 24 hours
    result_extended=True,
    
    # SQLite-specific tuning
    database_engine_options={
        "connect_args": {"check_same_thread": False},
    } if broker_type == "sqlite" else {},
    
    # Task routing
    task_routes={
        "app.tasks.analysis_tasks.*": {"queue": "analysis"},
    },
    
    # Task annotations
    task_annotations={
        "*": {
            "bind": True,
            "max_retries": 3,
            "default_retry_delay": 60,
        }
    },
)

# Export broker info for health checks
celery_app.conf.broker_type = broker_type
celery_app.conf.broker_available = broker_type == "redis"

logger.info(f"Celery app initialized with broker_type={broker_type}")
