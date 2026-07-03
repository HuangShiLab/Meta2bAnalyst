"""
Meta2bAnalyst - Analysis API Routes (Alpha/Beta/Differential/PCoA/NMDS)
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import AnalysisJob, DataFile, Session as SessionModel
from app.schemas import AnalysisRequest, AnalysisResponse, AnalysisResultResponse, ErrorResponse
from app.services.analysis_engine import (
    run_alpha_diversity,
    run_beta_diversity,
    run_differential_analysis,
    run_pcoa,
    run_nmds,
    run_heatmap,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_dataframe(session_id: str, db: DBSession) -> pd.DataFrame:
    """Get the feature table as a DataFrame for a session."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type.in_(["feature_table", "biom", "shared", "filtered_feature_table", "normalized_relative"]))
        .order_by(DataFile.id.desc())
        .first()
    )
    if not data_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feature table found for this session",
        )
    
    try:
        from app.services.data_parser import parse_data_file
        df, _ = parse_data_file(Path(data_file.file_path))
        return df
    except Exception as e:
        logger.error(f"Failed to parse data file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse data file: {str(e)}",
        )


def get_metadata_df(session_id: str, db: DBSession) -> Optional[pd.DataFrame]:
    """Get metadata DataFrame for a session if available."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type == "metadata")
        .first()
    )
    if not data_file:
        return None
    
    try:
        df = pd.read_csv(data_file.file_path, sep="\t", index_col=0)
        return df
    except Exception:
        return None


@router.post(
    "/sessions/{session_id}/analysis",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_analysis(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Submit an analysis job for a session."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    try:
        # Create analysis job record
        job = AnalysisJob(
            session_id=session_id,
            job_type=request.analysis_type,
            parameters={
                **request.parameters,
                "group_column": request.group_column,
                "comparisons": request.comparisons,
            },
            status="pending",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        logger.info(f"Created analysis job {job.id} for session {session_id} (type: {request.analysis_type})")
        
        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            parameters=job.parameters,
            created_at=job.created_at,
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create analysis job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create analysis job: {str(e)}",
        )


@router.get(
    "/sessions/{session_id}/analysis/{job_id}",
    response_model=AnalysisResultResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_analysis_result(
    session_id: str,
    job_id: int,
    db: DBSession = Depends(get_db),
):
    """Get analysis result for a job."""
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).filter(AnalysisJob.session_id == session_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job {job_id} not found for session {session_id}",
        )
    
    return AnalysisResultResponse(
        job_id=job.id,
        status=job.status,
        result_data=job.result_data,
        download_url=f"/api/v1/sessions/{session_id}/analysis/{job_id}/download" if job.result_path else None,
    )


@router.post(
    "/sessions/{session_id}/analysis/{job_id}/run",
    response_model=AnalysisResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def run_analysis(
    session_id: str,
    job_id: int,
    db: DBSession = Depends(get_db),
):
    """Run a pending analysis job (synchronous for now)."""
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).filter(AnalysisJob.session_id == session_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job {job_id} not found for session {session_id}",
        )
    
    if job.status not in ("pending", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Analysis job is already {job.status}",
        )
    
    # Get data
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    
    try:
        job.status = "running"
        job.started_at = datetime.datetime.utcnow()
        db.commit()
        
        result_data = None
        
        # Route to appropriate analysis engine
        if job.job_type == "alpha":
            result_data = run_alpha_diversity(df, metadata_df, job.parameters)
        elif job.job_type == "beta":
            result_data = run_beta_diversity(df, metadata_df, job.parameters)
        elif job.job_type == "differential":
            result_data = run_differential_analysis(df, metadata_df, job.parameters)
        elif job.job_type == "pcoa":
            result_data = run_pcoa(df, metadata_df, job.parameters)
        elif job.job_type == "nmds":
            result_data = run_nmds(df, metadata_df, job.parameters)
        elif job.job_type == "heatmap":
            result_data = run_heatmap(df, metadata_df, job.parameters)
        else:
            raise ValueError(f"Unknown analysis type: {job.job_type}")
        
        # Save result
        session_dir = Path("./uploads") / session_id / "results"
        session_dir.mkdir(parents=True, exist_ok=True)
        result_path = session_dir / f"analysis_{job_id}_{job.job_type}.json"
        
        import json
        with open(result_path, "w") as f:
            json.dump(result_data, f, indent=2, default=str)
        
        job.status = "completed"
        job.result_path = str(result_path)
        job.result_data = result_data
        job.completed_at = datetime.datetime.utcnow()
        db.commit()
        
        logger.info(f"Analysis job {job_id} completed successfully")
        
        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=job.result_data,
            completed_at=job.completed_at,
        )
    
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
        logger.error(f"Analysis job {job_id} failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}",
        )


import datetime
