"""
Meta2bAnalyst - FastAPI Application Entry Point
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import agent, analysis, data, export, multisite, sessions, strain, upload, workflows
from app.config import settings
from app.database import Base, engine

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
