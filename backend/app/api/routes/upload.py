"""
Meta2bAnalyst - File Upload API Routes
"""
import logging
import os
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.database import get_db
from app.models import DataFile, Session as SessionModel
from app.schemas import ErrorResponse, UploadListResponse, UploadResponse
from app.services.data_parser import detect_file_format, parse_data_file

logger = logging.getLogger(__name__)
router = APIRouter()


def get_file_extension(filename: str) -> str:
    """Extract file extension from filename."""
    return Path(filename).suffix.lower()


def validate_file_extension(filename: str) -> bool:
    """Check if file extension is allowed."""
    ext = get_file_extension(filename)
    return ext in settings.ALLOWED_EXTENSIONS


async def save_upload_file(
    upload_file: UploadFile,
    session_id: str,
    file_type: str,
) -> Path:
    """Save uploaded file to disk."""
    session_dir = Path(settings.UPLOAD_DIR) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize filename
    original_name = Path(upload_file.filename).name
    safe_name = f"{file_type}_{original_name}"
    file_path = session_dir / safe_name
    
    # Save file
    with open(file_path, "wb") as f:
        content = await upload_file.read()
        f.write(content)
    
    return file_path


@router.post(
    "/sessions/{session_id}/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_file(
    session_id: str,
    file_type: str = Form(..., description="File type: feature_table, biom, shared, taxonomy, metadata, strain"),
    file: UploadFile = File(...),
    db: DBSession = Depends(get_db),
):
    """Upload a data file to a session."""
    # Validate session exists
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided",
        )
    
    if not validate_file_extension(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )
    
    # Check file size
    file_content = await file.read()
    file_size = len(file_content)
    if file_size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum of {settings.MAX_FILE_SIZE / 1024 / 1024}MB",
        )
    
    # Reset file position for saving
    await file.seek(0)
    
    try:
        # Save file to disk
        file_path = await save_upload_file(file, session_id, file_type)
        
        # Parse file to get metadata
        row_count, column_count, sample_count, feature_count, sample_names, feature_names = None, None, None, None, None, None
        try:
            df, detected_format = parse_data_file(file_path, file_type)
            row_count = len(df)
            column_count = len(df.columns)
            
            # For feature tables, rows=features, columns=samples
            if file_type in ("feature_table", "biom", "shared"):
                sample_names = list(df.columns)
                feature_names = list(df.index)
                sample_count = len(df.columns)
                feature_count = len(df.index)
            elif file_type == "metadata":
                sample_names = list(df.index)
                feature_names = list(df.columns)
                sample_count = len(df.index)
                feature_count = len(df.columns)
            else:
                sample_names = list(df.columns)
                feature_names = list(df.index)
        except Exception as parse_error:
            logger.warning(f"File parsing failed for {file.filename}: {parse_error}")
            # File saved but parsing failed; still record it
        
        # Create database record
        data_file = DataFile(
            session_id=session_id,
            file_type=file_type,
            file_path=str(file_path),
            original_name=file.filename,
            file_size=file_size,
            row_count=row_count,
            column_count=column_count,
            sample_count=sample_count,
            feature_count=feature_count,
            sample_names=sample_names,
            feature_names=feature_names,
        )
        db.add(data_file)
        db.commit()
        db.refresh(data_file)
        
        # Update session status
        session.status = "uploading"
        db.commit()
        
        logger.info(f"Uploaded file {file.filename} to session {session_id} as {file_type}")
        
        return UploadResponse(
            file_id=data_file.id,
            session_id=session_id,
            file_type=file_type,
            original_name=file.filename,
            file_size=file_size,
            row_count=row_count,
            column_count=column_count,
            sample_count=sample_count,
            feature_count=feature_count,
            sample_names=sample_names,
            status="success",
            message="File uploaded successfully",
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload file for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )


@router.get(
    "/sessions/{session_id}/files",
    response_model=UploadListResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def list_files(
    session_id: str,
    db: DBSession = Depends(get_db),
):
    """List all uploaded files for a session."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    files = db.query(DataFile).filter(DataFile.session_id == session_id).all()
    return UploadListResponse(
        files=[
            UploadResponse(
                file_id=f.id,
                session_id=f.session_id,
                file_type=f.file_type,
                original_name=f.original_name or "unknown",
                file_size=f.file_size or 0,
                row_count=f.row_count,
                column_count=f.column_count,
                sample_count=f.sample_count,
                feature_count=f.feature_count,
                sample_names=f.sample_names,
                status="success",
                message="File available",
            )
            for f in files
        ]
    )
