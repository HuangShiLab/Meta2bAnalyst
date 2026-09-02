"""
Meta2bAnalyst - Session Management API Routes
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Session as SessionModel
from app.models import User
from app.utils.file_storage import delete_session_files
from app.schemas import (
    ErrorResponse,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
    SessionListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _request_user(request: Request) -> Optional[User]:
    """The auth middleware attaches request.state.user when AUTH_REQUIRED is
    on; tests and single-user deployments run with it off (user = None), in
    which case sessions behave as before: unowned and visible to all."""
    return getattr(request.state, "user", None)


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
        user_id=session.user_id,
    )


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_session(
    request: SessionCreate,
    http_request: Request,
    db: DBSession = Depends(get_db),
):
    """Create a new analysis session, owned by the authenticated user."""
    try:
        user = _request_user(http_request)
        session = SessionModel(
            name=request.name,
            data_format=request.data_format,
            analysis_level=request.analysis_level,
            description=request.description,
            metadata_json=request.metadata,
            status="created",
            user_id=user.id if user else None,
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
    http_request: Request,
    skip: int = 0,
    limit: int = 100,
    db: DBSession = Depends(get_db),
):
    """List sessions visible to the caller: an admin sees everything; other
    users see their own sessions plus shared (ownerless/demo) sessions."""
    try:
        query = db.query(SessionModel)
        user = _request_user(http_request)
        if user and user.role != "admin":
            query = query.filter(
                (SessionModel.user_id == user.id) | (SessionModel.user_id.is_(None))
            )
        total = query.count()
        sessions = query.offset(skip).limit(limit).all()
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
    force: bool = False,
    db: DBSession = Depends(get_db),
):
    """Delete a session, its database rows, and its uploaded files.

    Sessions created with ``metadata.demo = true`` (the preloaded classroom
    dataset) refuse deletion unless ``?force=true`` — on a shared instance any
    student can reach this endpoint, and losing the demo data mid-class is a
    much worse failure than an extra query parameter.
    """
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    if not force and isinstance(session.metadata_json, dict) and session.metadata_json.get("demo"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This is the shared demo session. Pass ?force=true to delete it anyway.",
        )
    try:
        db.delete(session)
        db.commit()

        # Remove the session's files too. This used to be a TODO, so deleting a
        # session left its uploads on disk forever -- on this machine that had
        # accumulated 230 orphaned directories against 65 live sessions. For a
        # service that ingests human subject data, "deleted" has to mean the
        # data is actually gone.
        if not delete_session_files(session_id):
            # The rows are already gone; report the leak rather than failing the
            # request, which the client cannot act on anyway.
            logger.error(f"Session {session_id} deleted but its files could not be removed")

        logger.info(f"Deleted session {session_id} and its uploaded files")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}",
        )
