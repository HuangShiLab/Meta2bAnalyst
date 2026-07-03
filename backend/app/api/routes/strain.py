"""
Meta2bAnalyst - Strain-Level Analysis API Routes
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import AnalysisJob, DataFile, Session as SessionModel
from app.schemas import ErrorResponse, StrainAnalysisRequest, StrainAnalysisResponse
from app.services.strain_analyzer import (
    run_strain_profile,
    run_strain_comparison,
    run_ani_matrix,
    run_strain_pcoa,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_strain_dataframe(session_id: str, db: DBSession) -> pd.DataFrame:
    """Get strain-level data for a session."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type == "strain")
        .first()
    )
    if not data_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No strain data found for this session",
        )
    
    try:
        df = pd.read_csv(data_file.file_path, sep="\t", index_col=0)
        return df
    except Exception as e:
        logger.error(f"Failed to parse strain data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse strain data: {str(e)}",
        )


@router.post(
    "/sessions/{session_id}/strain-analysis",
    response_model=StrainAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_strain_analysis(
    session_id: str,
    request: StrainAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Submit a strain-level analysis job."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    try:
        # Create analysis job
        job = AnalysisJob(
            session_id=session_id,
            job_type=f"strain_{request.analysis_type}",
            parameters={
                "species": request.species,
                "analysis_type": request.analysis_type,
                **request.parameters,
                "min_ani": request.min_ani,
                "min_coverage": request.min_coverage,
            },
            status="pending",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        logger.info(f"Created strain analysis job {job.id} for session {session_id}")
        
        return StrainAnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            species=request.species,
            analysis_type=request.analysis_type,
            status=job.status,
            message="Strain analysis job created",
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create strain analysis job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create strain analysis job: {str(e)}",
        )


@router.post(
    "/sessions/{session_id}/strain-analysis/{job_id}/run",
    response_model=StrainAnalysisResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def run_strain_analysis(
    session_id: str,
    job_id: int,
    db: DBSession = Depends(get_db),
):
    """Run a strain analysis job."""
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).filter(AnalysisJob.session_id == session_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strain analysis job {job_id} not found",
        )
    
    if job.status not in ("pending", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is already {job.status}",
        )
    
    try:
        df = get_strain_dataframe(session_id, db)
        params = job.parameters or {}
        species = params.get("species", "")
        analysis_type = params.get("analysis_type", "strain_profile")
        
        job.status = "running"
        db.commit()
        
        result_data = None
        strain_count = None
        
        if analysis_type == "strain_profile":
            result_data, strain_count = run_strain_profile(df, species, params)
        elif analysis_type == "strain_comparison":
            result_data = run_strain_comparison(df, species, params)
        elif analysis_type == "ani_matrix":
            result_data = run_ani_matrix(df, species, params)
        elif analysis_type == "strain_pcoa":
            result_data = run_strain_pcoa(df, species, params)
        else:
            raise ValueError(f"Unknown strain analysis type: {analysis_type}")
        
        # Save result
        import json
        import datetime
        
        session_dir = Path("./uploads") / session_id / "results"
        session_dir.mkdir(parents=True, exist_ok=True)
        result_path = session_dir / f"strain_analysis_{job_id}.json"
        
        with open(result_path, "w") as f:
            json.dump(result_data, f, indent=2, default=str)
        
        job.status = "completed"
        job.result_path = str(result_path)
        job.result_data = result_data
        db.commit()
        
        return StrainAnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            species=species,
            analysis_type=analysis_type,
            status=job.status,
            result_data=result_data,
            strain_count=strain_count,
            message="Strain analysis completed",
        )
    
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
        logger.error(f"Strain analysis job {job_id} failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Strain analysis failed: {str(e)}",
        )
