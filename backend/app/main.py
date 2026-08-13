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

from app.api.routes import agent, analysis, data, export, multisite, sessions, strain, upload
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors."""
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": exc.errors(),
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

logger.info("Meta2bAnalyst API initialized with all routes.")
