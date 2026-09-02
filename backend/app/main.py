"""
Meta2bAnalyst - FastAPI Application Entry Point
"""
import logging
import os
import re
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import agent, analysis, auth, data, export, multisite, sessions, strain, upload, workflows
from app.config import settings
from app.database import Base, SessionLocal, engine

# Configure logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/meta2banalyst.log"),
    ],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Meta2bAnalyst API starting up...")
    # Create tables if they don't exist
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified.")
        # create_all never alters existing tables: add sessions.user_id to
        # databases created before multi-user auth shipped.
        with engine.connect() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(sessions)").fetchall()]
            if "user_id" not in cols:
                conn.exec_driver_sql("ALTER TABLE sessions ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
                conn.commit()
                logger.info("Migrated sessions table: added user_id column.")
        # Seed the first admin account when auth is on and no users exist.
        if settings.AUTH_REQUIRED:
            from app.api.routes.auth import ensure_default_admin

            db = SessionLocal()
            try:
                ensure_default_admin(db)
            finally:
                db.close()
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
    yield
    logger.info("Meta2bAnalyst API shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Meta2bAnalyst API",
    description="Microbiome and Multi-omics Analysis Platform",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Authentication gate ──────────────────────────────────────────────────
# Guests (no token) may browse pages and run analyses on shared (ownerless)
# demo sessions. Anything that creates or mutates data — creating sessions,
# uploading files, filtering/normalizing shared data, deleting, saving
# workflow templates — requires a signed-in account. Authenticated users
# additionally get ownership checks on session-scoped paths: the owner and
# admins may proceed; ownerless sessions (demo data) stay shared.
_PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}
_SESSION_PATH_RE = re.compile(r"^/api/v1/sessions/([^/]+)")
# Session sub-paths that mutate stored data; blocked for guests.
_GUEST_BLOCKED_SESSION_SUBPATHS = (
    "/upload",
    "/upload-chunk",
    "/upload-chunk-complete",
    "/filter",
    "/normalize",
)

_GUEST_401 = {"detail": "Sign in to upload or modify your own data"}


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    if not settings.AUTH_REQUIRED:
        return await call_next(request)
    path = request.url.path
    if (
        request.method == "OPTIONS"
        or path in _PUBLIC_PATHS
        or path.startswith("/api/v1/auth/")
        or not path.startswith("/api/")
    ):
        return await call_next(request)

    from app.models import Session as SessionModel, User
    from app.services.auth import user_can_access_session, verify_token

    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else request.cookies.get("m2b_token")
    payload = verify_token(token) if token else None
    if token and not payload:
        # A token was presented but is invalid/expired — not a guest.
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

    db = SessionLocal()
    try:
        user = None
        if payload:
            user = db.query(User).filter(User.id == payload["sub"]).first()
            if not user or not user.is_active:
                return JSONResponse(status_code=401, content={"detail": "Account disabled or removed"})
            request.state.user = user

        match = _SESSION_PATH_RE.match(path)
        if user is None:
            # ── Guest rules ──
            if request.method == "POST" and path == "/api/v1/sessions":
                return JSONResponse(status_code=401, content=_GUEST_401)
            if request.method == "POST" and path == "/api/v1/workflows":
                return JSONResponse(status_code=401, content=_GUEST_401)
            if match:
                sess = db.query(SessionModel).filter(SessionModel.id == match.group(1)).first()
                if sess and sess.user_id is not None:
                    # Someone's private session: guests may not touch it.
                    return JSONResponse(status_code=401, content=_GUEST_401)
                if sess:
                    rest = path[match.end():]
                    if request.method == "DELETE" or any(
                        rest.startswith(sub) for sub in _GUEST_BLOCKED_SESSION_SUBPATHS
                    ):
                        return JSONResponse(status_code=401, content=_GUEST_401)
        elif match:
            sess = db.query(SessionModel).filter(SessionModel.id == match.group(1)).first()
            if sess and not user_can_access_session(user, sess):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "You do not have access to this session"},
                )
    finally:
        db.close()

    return await call_next(request)


def _field_path(error: dict) -> str:
    """Render one validation error's ``loc`` as a dotted field path."""
    parts = [str(p) for p in error.get("loc", []) if p is not None]
    return ".".join(parts) if parts else "body"


def summarize_validation_errors(errors: list) -> str:
    """One-line, human-readable summary that names every offending field.

    Clients (and the pipeline smoke harness) surface ``detail`` and nothing
    else, so a bare "Validation error" tells the caller nothing about which
    field it got wrong.
    """
    return "; ".join(f"{_field_path(e)}: {e.get('msg', 'invalid value')}" for e in errors)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors.

    Pydantic v2 puts the original exception object in each error's ``ctx``,
    which is not JSON-serialisable. Passing ``exc.errors()`` straight into a
    JSONResponse makes this handler itself raise, turning every 422 into an
    opaque, body-less 500. ``jsonable_encoder`` coerces those objects to
    strings so the client actually receives the validation detail.

    ``detail`` names the offending fields inline; ``fields`` repeats them as a
    machine-readable list and ``errors`` keeps the raw Pydantic payload.
    """
    errors = jsonable_encoder(exc.errors())
    summary = summarize_validation_errors(errors)
    logger.error(f"Validation error: {errors}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": f"Validation error: {summary}" if summary else "Validation error",
            "fields": [_field_path(e) for e in errors],
            "errors": errors,
        },
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Meta2bAnalyst API",
        "version": "0.2.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "meta2banalyst-api"}


# API v1 router
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
app.include_router(upload.router, prefix="/api/v1", tags=["upload"])
app.include_router(data.router, prefix="/api/v1", tags=["data"])
app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])
app.include_router(agent.router, prefix="/api/v1", tags=["agent"])
app.include_router(multisite.router, prefix="/api/v1", tags=["multisite"])
app.include_router(strain.router, prefix="/api/v1", tags=["strain"])
app.include_router(export.router, prefix="/api/v1", tags=["export"])
app.include_router(workflows.router, prefix="/api/v1", tags=["workflows"])

logger.info("Meta2bAnalyst API initialized with all routes.")
