"""
Meta2bAnalyst - Session Management API Routes
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Session as SessionModel
from app.schemas import (
    ErrorResponse,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
    SessionListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def session_to_response(session: SessionModel) -> SessionResponse:
    """Convert a Session model to a SessionResponse schema."""
    return SessionResponse(
        id=session.id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        name=session.name,
        data_format=session.data_format,
        analysis_level=session.analysis_level,
        status=session.status,
        description=session.description,
        file_count=len(session.data_files),
    )


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_session(
    request: SessionCreate,
    db: DBSession = Depends(get_db),
):
    """Create a new analysis session."""
    try:
        session = SessionModel(
            name=request.name,
            data_format=request.data_format,
            analysis_level=request.analysis_level,
            description=request.description,
            metadata_json=request.metadata,
            status="created",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info(f"Created session {session.id}")
        return session_to_response(session)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}",
        )


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    responses={500: {"model": ErrorResponse}},
)
async def list_sessions(
    skip: int = 0,
    limit: int = 100,
    db: DBSession = Depends(get_db),
):
    """List all analysis sessions."""
    try:
        sessions = db.query(SessionModel).offset(skip).limit(limit).all()
        total = db.query(SessionModel).count()
        return SessionListResponse(
            sessions=[session_to_response(s) for s in sessions],
            total=total,
        )
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sessions: {str(e)}",
        )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_session(
    session_id: str,
    db: DBSession = Depends(get_db),
):
    """Get a session by ID."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return session_to_response(session)


@router.put(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def update_session(
    session_id: str,
    request: SessionUpdate,
    db: DBSession = Depends(get_db),
):
    """Update a session."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    try:
        if request.name is not None:
            session.name = request.name
        if request.status is not None:
            session.status = request.status
        if request.description is not None:
            session.description = request.description
        db.commit()
        db.refresh(session)
        logger.info(f"Updated session {session_id}")
        return session_to_response(session)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {str(e)}",
        )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def delete_session(
    session_id: str,
    db: DBSession = Depends(get_db),
):
    """Delete a session and all associated data."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    try:
        # TODO: Delete uploaded files from disk
        db.delete(session)
        db.commit()
        logger.info(f"Deleted session {session_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}",
        )
