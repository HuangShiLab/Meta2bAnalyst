"""
Meta2bAnalyst - FastAPI Application Entry Point
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analysis, data, export, sessions, strain, upload
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
    # Startup
    logger.info("Starting up Meta2bAnalyst backend...")
    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created.")
    yield
    # Shutdown
    logger.info("Shutting down Meta2bAnalyst backend...")


app = FastAPI(
    title="Meta2bAnalyst API",
    description="Scientific data analysis platform backend for microbiome data",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "message": str(exc) if settings.DEBUG else "An unexpected error occurred",
        },
    )


# Health check endpoint
@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "database": "connected",
    }


# API v1 router
app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
app.include_router(upload.router, prefix="/api/v1", tags=["upload"])
app.include_router(data.router, prefix="/api/v1", tags=["data"])
app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])
app.include_router(strain.router, prefix="/api/v1", tags=["strain"])
app.include_router(export.router, prefix="/api/v1", tags=["export"])

logger.info("Meta2bAnalyst API initialized with all routes.")
