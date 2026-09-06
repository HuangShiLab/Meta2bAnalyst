"""
Multi-site Analysis API Routes
================================
Provides endpoints for analyzing microbiome data across multiple sites,
body sites, cohorts, or timepoints.

Endpoints:
- POST /sessions/{session_id}/analyze/multisite-pcoa
- POST /sessions/{session_id}/analyze/multisite-permanova
- POST /sessions/{session_id}/analyze/multisite-markers
- POST /sessions/{session_id}/analyze/multisite-temporal
- POST /sessions/{session_id}/analyze/multisite-network-compare
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import AnalysisJob, Session as SessionModel
from app.schemas import AnalysisResponse, ErrorResponse
from app.api.routes.analysis import get_all_dataframes_by_type, get_dataframe, get_metadata_df
from app.services.multisite_analysis import (
    run_multisite_pcoa,
    run_multisite_permanova,
    run_multisite_markers,
    run_multisite_temporal,
    run_multisite_network_compare,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_multisite_data(session_id: str, db: DBSession):
    """Merge every per-site table into one features x samples matrix plus a
    concatenated metadata frame.

    Multi-site sessions carry one feature table + one metadata file per body
    site; get_dataframe()/get_metadata_df() silently return only the most
    recently uploaded file, which would run "cross-site" analyses on a single
    site. Feature tables are outer-joined on the feature index (a feature
    absent from one site gets abundance 0 there); metadata frames are
    row-concatenated, first occurrence wins on duplicate sample IDs.
    """
    import pandas as pd
    from pathlib import Path
    from app.models import DataFile
    from app.services.data_parser import parse_data_file

    meta_files = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type == 'metadata')
        .order_by(DataFile.id.asc())
        .all()
    )
    frames = []
    for mf in meta_files:
        try:
            frame = pd.read_csv(mf.file_path, sep='\t', index_col=0)
            if frame.shape[1] <= 1:
                frame = pd.read_csv(mf.file_path, index_col=0)
            frames.append(frame)
        except Exception:
            logger.warning(f'Could not parse metadata file {mf.file_path}', exc_info=True)
    metadata_df = None
    if frames:
        metadata_df = frames[0] if len(frames) == 1 else pd.concat(frames)
        metadata_df = metadata_df[~metadata_df.index.duplicated(keep='first')]
    sample_ids = {str(i) for i in metadata_df.index} if metadata_df is not None else set()

    # Load every per-site microbiome table directly. get_all_dataframes_by_type
    # validates sample IDs against get_metadata_df(), which only sees the most
    # recently uploaded metadata file — per-site tables whose samples live in
    # another site's metadata would be silently dropped.
    ft_files = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type == 'microbiome')
        .order_by(DataFile.id.asc())
        .all()
    )
    if not ft_files:
        return get_dataframe(session_id, db), metadata_df

    merged = None
    for f in ft_files:
        t, _ = parse_data_file(Path(f.file_path), file_type='microbiome')
        # Orient to features x samples by comparing labels with metadata IDs.
        if sample_ids:
            col_hits = sum(1 for c in t.columns if str(c) in sample_ids)
            row_hits = sum(1 for i in t.index if str(i) in sample_ids)
            if row_hits > col_hits:
                t = t.T
        if merged is None:
            merged = t
        else:
            merged = merged.join(t, how='outer', rsuffix='__dup')
            dup_cols = [c for c in merged.columns if str(c).endswith('__dup')]
            if dup_cols:
                logger.warning(f'Duplicate sample IDs across site tables in {f.original_name}: {dup_cols}')
                merged = merged.drop(columns=dup_cols)
    df = merged.fillna(0) if merged is not None else get_dataframe(session_id, db)
    return df, metadata_df


def _error_status(e: Exception) -> int:
    """Map analysis exceptions to HTTP codes: bad input/columns are client
    errors (400), everything else is a server error (500)."""
    return 400 if isinstance(e, (ValueError, KeyError)) else 500


def _sanitize_json(obj: Any) -> Any:
    """Recursively convert numpy types to native Python so result_data is JSON-serializable."""
    import numpy as np
    import pandas as pd
    if isinstance(obj, dict):
        return {str(k): _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, pd.DataFrame):
        return _sanitize_json(obj.to_dict(orient="records"))
    if isinstance(obj, pd.Series):
        return _sanitize_json(obj.to_dict())
    return obj


# ─────────────────────────────── Request Models

class MultiSitePCoARequest(BaseModel):
    """Request for multi-site PCoA."""
    site_column: Optional[str] = Field(default=None, description="Metadata column for site grouping")
    subject_column: Optional[str] = Field(default=None, description="Metadata column for subject ID (paired)")
    group_column: Optional[str] = Field(default=None, description="Metadata column for additional grouping")
    distance_metric: str = Field(default="braycurtis", description="Distance metric: braycurtis, jaccard, euclidean")
    ordination_method: str = Field(default="pcoa", description="Ordination: pcoa or nmds")
    connect_subjects: bool = Field(default=False, description="Connect paired subjects across sites")


class MultiSitePERMANOVARequest(BaseModel):
    """Request for multi-site PERMANOVA."""
    site_column: Optional[str] = Field(default=None, description="Metadata column for site")
    group_column: Optional[str] = Field(default=None, description="Metadata column for group")
    distance_metric: str = Field(default="braycurtis")
    permutations: int = Field(default=999, ge=99, le=9999)


class MultiSiteMarkerRequest(BaseModel):
    """Request for multi-site marker discovery."""
    site_column: Optional[str] = Field(default=None, description="Metadata column for site")
    reference_site: Optional[str] = Field(default=None, description="Reference site for comparison")
    subject_column: Optional[str] = Field(default=None, description="Subject column for paired analysis")
    pvalue_threshold: float = Field(default=0.05, ge=0.001, le=0.1)
    fc_threshold: float = Field(default=1.5, ge=1.2, le=4.0)


class MultiSiteTemporalRequest(BaseModel):
    """Request for multi-site temporal analysis."""
    time_column: Optional[str] = Field(default=None, description="Metadata column for timepoint")
    subject_column: Optional[str] = Field(default=None, description="Subject column")
    group_column: Optional[str] = Field(default=None)
    site_column: Optional[str] = Field(default=None)
    distance_metric: str = Field(default="braycurtis")


class MultiSiteNetworkRequest(BaseModel):
    """Request for multi-site network comparison."""
    site_column: Optional[str] = Field(default=None, description="Metadata column for site")
    threshold: float = Field(default=0.3, ge=0.1, le=0.8, description="SparCC correlation threshold")


# ─────────────────────────────── Helper

def _create_job(db: DBSession, session_id: str, job_type: str, params: Dict[str, Any]) -> AnalysisJob:
    """Create and save an analysis job record."""
    job = AnalysisJob(
        session_id=session_id,
        job_type=job_type,
        parameters=params,
        status='running',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# ─────────────────────────────── 1. Multi-site PCoA

@router.post(
    '/sessions/{session_id}/analyze/multisite-pcoa',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_multisite_pcoa(
    session_id: str,
    request: MultiSitePCoARequest,
    db: DBSession = Depends(get_db),
):
    """Run multi-site PCoA with all sites overlaid."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    # get_dataframe returns the canonical features x samples orientation
    # (app/services/orientation.py); every multisite service documents its input
    # as samples x taxa, so transpose once here.
    df, metadata_df = _get_multisite_data(session_id, db)
    df = df.T
    if metadata_df is None:
        raise HTTPException(status_code=400, detail='Metadata required for multi-site analysis')

    job = _create_job(db, session_id, 'multisite_pcoa', request.model_dump())

    try:
        result = run_multisite_pcoa(
            df, metadata_df,
            site_column=request.site_column,
            subject_column=request.subject_column,
            group_column=request.group_column,
            distance_metric=request.distance_metric,
            ordination_method=request.ordination_method,
            connect_subjects=request.connect_subjects,
        )
        job.status = 'completed'
        job.result_data = _sanitize_json(result)
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type='multisite_pcoa',
            status='completed',
            parameters=job.parameters,
            result_data=job.result_data,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
    except Exception as e:
        logger.error(f'Multi-site PCoA failed: {e}', exc_info=True)
        job.status = 'failed'
        job.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=_error_status(e), detail=f'Multi-site PCoA failed: {str(e)}')


# ─────────────────────────────── 2. Multi-site PERMANOVA

@router.post(
    '/sessions/{session_id}/analyze/multisite-permanova',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_multisite_permanova(
    session_id: str,
    request: MultiSitePERMANOVARequest,
    db: DBSession = Depends(get_db),
):
    """Run PERMANOVA testing site effects and interactions."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    # get_dataframe returns the canonical features x samples orientation
    # (app/services/orientation.py); every multisite service documents its input
    # as samples x taxa, so transpose once here.
    df, metadata_df = _get_multisite_data(session_id, db)
    df = df.T
    if metadata_df is None:
        raise HTTPException(status_code=400, detail='Metadata required')

    job = _create_job(db, session_id, 'multisite_permanova', request.model_dump())

    try:
        result = run_multisite_permanova(
            df, metadata_df,
            site_column=request.site_column,
            group_column=request.group_column,
            distance_metric=request.distance_metric,
            permutations=request.permutations,
        )
        job.status = 'completed'
        job.result_data = _sanitize_json(result)
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type='multisite_permanova',
            status='completed',
            parameters=job.parameters,
            result_data=job.result_data,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
    except Exception as e:
        logger.error(f'Multi-site PERMANOVA failed: {e}', exc_info=True)
        job.status = 'failed'
        job.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=_error_status(e), detail=f'Multi-site PERMANOVA failed: {str(e)}')


# ─────────────────────────────── 3. Multi-site Markers

@router.post(
    '/sessions/{session_id}/analyze/multisite-markers',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_multisite_markers(
    session_id: str,
    request: MultiSiteMarkerRequest,
    db: DBSession = Depends(get_db),
):
    """Discover site-specific differential abundance markers."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    # get_dataframe returns the canonical features x samples orientation
    # (app/services/orientation.py); every multisite service documents its input
    # as samples x taxa, so transpose once here.
    df, metadata_df = _get_multisite_data(session_id, db)
    df = df.T
    if metadata_df is None:
        raise HTTPException(status_code=400, detail='Metadata required')

    job = _create_job(db, session_id, 'multisite_markers', request.model_dump())

    try:
        result = run_multisite_markers(
            df, metadata_df,
            site_column=request.site_column,
            reference_site=request.reference_site,
            subject_column=request.subject_column,
            pvalue_threshold=request.pvalue_threshold,
            fc_threshold=request.fc_threshold,
        )
        job.status = 'completed'
        job.result_data = _sanitize_json(result)
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type='multisite_markers',
            status='completed',
            parameters=job.parameters,
            result_data=job.result_data,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
    except Exception as e:
        logger.error(f'Multi-site markers failed: {e}', exc_info=True)
        job.status = 'failed'
        job.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=_error_status(e), detail=f'Multi-site markers failed: {str(e)}')


# ─────────────────────────────── 4. Multi-site Temporal

@router.post(
    '/sessions/{session_id}/analyze/multisite-temporal',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_multisite_temporal(
    session_id: str,
    request: MultiSiteTemporalRequest,
    db: DBSession = Depends(get_db),
):
    """Run longitudinal trajectory analysis across timepoints."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    # get_dataframe returns the canonical features x samples orientation
    # (app/services/orientation.py); every multisite service documents its input
    # as samples x taxa, so transpose once here.
    df, metadata_df = _get_multisite_data(session_id, db)
    df = df.T
    if metadata_df is None:
        raise HTTPException(status_code=400, detail='Metadata required')

    job = _create_job(db, session_id, 'multisite_temporal', request.model_dump())

    try:
        result = run_multisite_temporal(
            df, metadata_df,
            time_column=request.time_column,
            subject_column=request.subject_column,
            group_column=request.group_column,
            site_column=request.site_column,
            distance_metric=request.distance_metric,
        )
        job.status = 'completed'
        job.result_data = _sanitize_json(result)
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type='multisite_temporal',
            status='completed',
            parameters=job.parameters,
            result_data=job.result_data,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
    except Exception as e:
        logger.error(f'Multi-site temporal failed: {e}', exc_info=True)
        job.status = 'failed'
        job.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=_error_status(e), detail=f'Multi-site temporal failed: {str(e)}')


# ─────────────────────────────── 5. Multi-site Network Compare

@router.post(
    '/sessions/{session_id}/analyze/multisite-network-compare',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_multisite_network_compare(
    session_id: str,
    request: MultiSiteNetworkRequest,
    db: DBSession = Depends(get_db),
):
    """Compare correlation networks across sites."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    # get_dataframe returns the canonical features x samples orientation
    # (app/services/orientation.py); every multisite service documents its input
    # as samples x taxa, so transpose once here.
    df, metadata_df = _get_multisite_data(session_id, db)
    df = df.T
    if metadata_df is None:
        raise HTTPException(status_code=400, detail='Metadata required')

    job = _create_job(db, session_id, 'multisite_network_compare', request.model_dump())

    try:
        result = run_multisite_network_compare(
            df, metadata_df,
            site_column=request.site_column,
            threshold=request.threshold,
        )
        job.status = 'completed'
        job.result_data = _sanitize_json(result)
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type='multisite_network_compare',
            status='completed',
            parameters=job.parameters,
            result_data=job.result_data,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
    except Exception as e:
        logger.error(f'Multi-site network compare failed: {e}', exc_info=True)
        job.status = 'failed'
        job.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=_error_status(e), detail=f'Multi-site network compare failed: {str(e)}')
