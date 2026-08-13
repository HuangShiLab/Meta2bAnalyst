"""
Meta2bAnalyst - Export API Routes
"""
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.database import get_db
from app.models import AnalysisJob, DataFile, Session as SessionModel
from app.schemas import ErrorResponse, ExportRequest, ExportResponse
from app.services.export_service import export_data, export_result, export_plot

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/sessions/{session_id}/export",
    response_model=ExportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_export(
    session_id: str,
    request: ExportRequest,
    db: DBSession = Depends(get_db),
):
    """Export data or results in the requested format."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    try:
        # Determine export directory
        export_dir = Path(settings.UPLOAD_DIR) / session_id / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        
        export_path = None
        
        if request.export_type == "data":
            # Export data file
            if request.file_id:
                data_file = db.query(DataFile).filter(DataFile.id == request.file_id).first()
            else:
                data_file = (
                    db.query(DataFile)
                    .filter(DataFile.session_id == session_id)
                    .filter(DataFile.file_type.in_(["feature_table", "filtered_feature_table", "normalized_relative"]))
                    .order_by(DataFile.id.desc())
                    .first()
                )
            
            if not data_file:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No data file found to export",
                )
            
            export_path = export_dir / f"data_export.{request.format}"
            export_data(data_file.file_path, str(export_path), request.format, request.parameters)
        
        elif request.export_type == "result":
            # Export analysis result
            if not request.job_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="job_id is required for result export",
                )
            
            job = db.query(AnalysisJob).filter(AnalysisJob.id == request.job_id).first()
            if not job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Analysis job {request.job_id} not found",
                )
            
            export_path = export_dir / f"result_{request.job_id}.{request.format}"
            export_result(job.result_data, str(export_path), request.format, request.parameters)
        
        elif request.export_type == "plot":
            # Export plot
            export_path = export_dir / f"plot_export.{request.format}"
            export_plot(session_id, str(export_path), request.format, request.parameters)
        
        elif request.export_type == "report":
            # Export full report (PDF)
            export_path = export_dir / f"report.{request.format}"
            # Gather all analysis results for this session
            jobs = (
                db.query(AnalysisJob)
                .filter(AnalysisJob.session_id == session_id)
                .filter(AnalysisJob.status == "completed")
                .order_by(AnalysisJob.created_at)
                .all()
            )
            analysis_results = []
            for job in jobs:
                if job.result_data:
                    analysis_results.append({
                        "test_method": job.job_type,
                        "parameters": job.parameters,
                        **job.result_data,
                    })
            from app.services.export_service import generate_comprehensive_report
            generate_comprehensive_report(
                session_id=session_id,
                export_path=str(export_path),
                analysis_results=analysis_results,
            )
        
        elif request.export_type == "metadata":
            # Export metadata
            data_file = (
                db.query(DataFile)
                .filter(DataFile.session_id == session_id)
                .filter(DataFile.file_type == "metadata")
                .first()
            )
            if not data_file:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No metadata file found",
                )
            export_path = export_dir / f"metadata.{request.format}"
            export_data(data_file.file_path, str(export_path), request.format, request.parameters)
        
        if not export_path or not export_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Export failed: output file not created",
            )
        
        file_size = export_path.stat().st_size
        export_id = f"{session_id}_{request.export_type}_{request.format}"
        
        return ExportResponse(
            export_id=export_id,
            session_id=session_id,
            export_type=request.export_type,
            format=request.format,
            file_path=str(export_path),
            file_size=file_size,
            download_url=f"/api/v1/sessions/{session_id}/export/download?export_id={export_id}",
            status="success",
            message="Export completed successfully",
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export failed for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}",
        )


@router.post(
    "/sessions/{session_id}/export/report",
    status_code=status.HTTP_200_OK,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def download_report(
    session_id: str,
    db: DBSession = Depends(get_db),
):
    """Generate and download a comprehensive PDF report."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    try:
        export_dir = Path(settings.UPLOAD_DIR) / session_id / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / f"report_{session_id}.pdf"
        
        jobs = (
            db.query(AnalysisJob)
            .filter(AnalysisJob.session_id == session_id)
            .filter(AnalysisJob.status == "completed")
            .order_by(AnalysisJob.created_at)
            .all()
        )
        analysis_results = []
        for job in jobs:
            if job.result_data:
                analysis_results.append({
                    "test_method": job.job_type,
                    "parameters": job.parameters,
                    **job.result_data,
                })
        
        # Gather preprocessing info from data files
        data_files = db.query(DataFile).filter(DataFile.session_id == session_id).all()
        preprocessing_info = {}
        for df in data_files:
            ft = df.file_type
            if ft == 'filtered_feature_table':
                preprocessing_info['filtering'] = 'Applied (filtered_feature_table)'
            elif ft == 'normalized_tss':
                preprocessing_info['normalization'] = 'TSS (Total Sum Scaling)'
            elif ft == 'normalized_rarefaction':
                preprocessing_info['normalization'] = 'Rarefaction'
            elif ft == 'normalized_clr':
                preprocessing_info['normalization'] = 'CLR (Centered Log-Ratio)'
            elif ft == 'normalized_css':
                preprocessing_info['normalization'] = 'CSS (Cumulative Sum Scaling)'
        
        from app.services.export_service import generate_comprehensive_report
        try:
            generate_comprehensive_report(
                session_id=session_id,
                export_path=str(export_path),
                analysis_results=analysis_results,
                preprocessing_info=preprocessing_info,
            )
        except Exception as e:
            import traceback
            logger.error(f"Report generation traceback:\n{traceback.format_exc()}")
            raise
        
        return FileResponse(
            path=str(export_path),
            filename=f"Meta2bAnalyst_Report_{session_id}.pdf",
            media_type="application/pdf",
        )
    
    except Exception as e:
        logger.error(f"Report generation failed for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {str(e)}",
        )


@router.get("/sessions/{session_id}/export/download")
async def download_export(
    session_id: str,
    export_id: str,
    db: DBSession = Depends(get_db),
):
    """Download an exported file."""
    # Parse export_id to find the file
    export_dir = Path(settings.UPLOAD_DIR) / session_id / "exports"
    
    # Find the most recently exported file matching the pattern
    files = list(export_dir.iterdir()) if export_dir.exists() else []
    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found",
        )
    
    latest_file = max(files, key=lambda p: p.stat().st_mtime)
    
    return FileResponse(
        path=str(latest_file),
        filename=latest_file.name,
        media_type="application/octet-stream",
    )
