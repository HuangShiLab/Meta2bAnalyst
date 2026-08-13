"""
Meta2bAnalyst - File Upload API Routes
Supports chunked upload for large files and progress tracking.
"""
import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional

import aiofiles
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

# Chunk upload state storage (in-memory; for production use Redis or DB)
_chunk_uploads: dict[str, dict] = {}


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


# ─────────────────────────────── Chunked Upload

@router.post(
    "/sessions/{session_id}/upload-chunk",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_chunk(
    session_id: str,
    chunk: UploadFile = File(...),
    upload_id: str = Form(..., description="Unique upload identifier (UUID)"),
    chunk_index: int = Form(..., ge=0, description="Chunk index starting from 0"),
    total_chunks: int = Form(..., ge=1, description="Total number of chunks"),
    file_type: str = Form(..., description="File type: feature_table, biom, shared, taxonomy, metadata, strain, microbiome, metabolome, metaphlan, humann3"),
    original_filename: str = Form(..., description="Original filename"),
    db: DBSession = Depends(get_db),
):
    """Upload a single chunk of a large file.
    
    Client must call /upload-chunk-complete after all chunks are uploaded.
    """
    # Validate session
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    if not validate_file_extension(original_filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )
    
    # Initialize chunk upload state
    upload_key = f"{session_id}:{upload_id}"
    if upload_key not in _chunk_uploads:
        _chunk_uploads[upload_key] = {
            "upload_id": upload_id,
            "session_id": session_id,
            "file_type": file_type,
            "original_filename": original_filename,
            "total_chunks": total_chunks,
            "received_chunks": set(),
            "chunk_dir": Path(settings.UPLOAD_DIR) / session_id / "chunks" / upload_id,
        }
        _chunk_uploads[upload_key]["chunk_dir"].mkdir(parents=True, exist_ok=True)
    
    upload_state = _chunk_uploads[upload_key]
    
    # Save chunk to disk
    chunk_path = upload_state["chunk_dir"] / f"chunk_{chunk_index:05d}"
    try:
        async with aiofiles.open(chunk_path, "wb") as f:
            content = await chunk.read()
            await f.write(content)
        upload_state["received_chunks"].add(chunk_index)
    except Exception as e:
        logger.error(f"Failed to save chunk {chunk_index} for upload {upload_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save chunk: {str(e)}",
        )
    
    received = len(upload_state["received_chunks"])
    progress = int((received / total_chunks) * 100)
    
    logger.info(f"Chunk upload {upload_id}: chunk {chunk_index + 1}/{total_chunks} ({progress}%)")
    
    return {
        "upload_id": upload_id,
        "chunk_index": chunk_index,
        "received_chunks": received,
        "total_chunks": total_chunks,
        "progress": progress,
        "status": "chunk_received" if received < total_chunks else "complete",
    }


@router.post(
    "/sessions/{session_id}/upload-chunk-complete",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def complete_chunk_upload(
    session_id: str,
    upload_id: str = Form(..., description="Upload ID from chunked upload"),
    db: DBSession = Depends(get_db),
):
    """Complete a chunked upload by assembling all chunks into a single file."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    upload_key = f"{session_id}:{upload_id}"
    if upload_key not in _chunk_uploads:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload {upload_id} not found. Start chunked upload first.",
        )
    
    upload_state = _chunk_uploads[upload_key]
    total_chunks = upload_state["total_chunks"]
    received = upload_state["received_chunks"]
    
    if len(received) < total_chunks:
        missing = [i for i in range(total_chunks) if i not in received]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Incomplete upload. Missing chunks: {missing}",
        )
    
    # Assemble chunks
    session_dir = Path(settings.UPLOAD_DIR) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    safe_name = f"{upload_state['file_type']}_{upload_state['original_filename']}"
    file_path = session_dir / safe_name
    
    try:
        with open(file_path, "wb") as out_f:
            for i in range(total_chunks):
                chunk_path = upload_state["chunk_dir"] / f"chunk_{i:05d}"
                with open(chunk_path, "rb") as chunk_f:
                    shutil.copyfileobj(chunk_f, out_f)
        
        # Clean up chunks
        shutil.rmtree(upload_state["chunk_dir"], ignore_errors=True)
        del _chunk_uploads[upload_key]
        
        logger.info(f"Assembled chunked upload {upload_id} into {file_path}")
    except Exception as e:
        logger.error(f"Failed to assemble chunks for upload {upload_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assemble file: {str(e)}",
        )
    
    # Parse and record
    file_size = os.path.getsize(file_path)
    row_count, column_count, sample_count, feature_count, sample_names, feature_names = None, None, None, None, None, None
    try:
        df, detected_format = parse_data_file(file_path, upload_state["file_type"], use_chunks=True)
        row_count = len(df)
        column_count = len(df.columns)
        
        if upload_state["file_type"] in ("feature_table", "biom", "shared", "microbiome", "metabolome"):
            sample_names = list(df.columns)
            feature_names = list(df.index)
            sample_count = len(df.columns)
            feature_count = len(df.index)
        elif upload_state["file_type"] == "metadata":
            sample_names = list(df.index)
            feature_names = list(df.columns)
            sample_count = len(df.index)
            feature_count = len(df.columns)
        else:
            sample_names = list(df.columns)
            feature_names = list(df.index)
    except Exception as parse_error:
        logger.warning(f"File parsing failed for {upload_state['original_filename']}: {parse_error}")
    
    data_file = DataFile(
        session_id=session_id,
        file_type=upload_state["file_type"],
        file_path=str(file_path),
        original_name=upload_state["original_filename"],
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
    
    session.status = "uploading"
    db.commit()
    
    return UploadResponse(
        file_id=data_file.id,
        session_id=session_id,
        file_type=upload_state["file_type"],
        original_name=upload_state["original_filename"],
        file_size=file_size,
        row_count=row_count,
        column_count=column_count,
        sample_count=sample_count,
        feature_count=feature_count,
        sample_names=sample_names,
        status="success",
        message="Chunked upload completed successfully",
    )


@router.get(
    "/uploads/{upload_id}/progress",
    responses={404: {"model": ErrorResponse}},
)
async def get_upload_progress(upload_id: str, session_id: str):
    """Get upload progress for a chunked upload."""
    upload_key = f"{session_id}:{upload_id}"
    if upload_key not in _chunk_uploads:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload {upload_id} not found",
        )
    
    upload_state = _chunk_uploads[upload_key]
    received = len(upload_state["received_chunks"])
    total = upload_state["total_chunks"]
    
    return {
        "upload_id": upload_id,
        "received_chunks": received,
        "total_chunks": total,
        "progress": int((received / total) * 100),
        "missing_chunks": [i for i in range(total) if i not in upload_state["received_chunks"]],
    }


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
    file_type: str = Form(..., description="File type: feature_table, biom, shared, taxonomy, metadata, strain, microbiome, metabolome, metaphlan, humann3"),
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
            if file_type in ("feature_table", "biom", "shared", "microbiome", "metabolome", "metaphlan", "humann3"):
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
