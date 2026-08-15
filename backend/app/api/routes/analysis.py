"""
Meta2bAnalyst - Analysis API Routes (Alpha/Beta/Differential/PCoA/NMDS/Heatmap/StackedBar/RF/PERMANOVA/ANOSIM)
Provides direct endpoints for each analysis type with Plotly JSON output.
Supports both synchronous (fast) and asynchronous (Celery) execution modes.
"""
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session as DBSession

from app.celery_app import celery_app
from app.config import settings
from app.database import get_db
from app.models import AnalysisJob, DataFile, Session as SessionModel
from app.schemas import AnalysisRequest, AnalysisResponse, AnalysisResultResponse, ErrorResponse
from app.services.r_analysis import (
    ApproximationRefused,
    engine_for as r_engine_for,
    run_ancombc,
    run_deseq2,
    run_edger,
    run_maaslin3,
    run_lefse,
)
from app.services.analysis_engine import (
    AnalysisEngine,
    resolve_comparison_groups,
    run_alpha_diversity,
    run_beta_diversity,
    run_differential_analysis,
    run_pcoa,
    run_nmds,
    run_heatmap,
    run_permanova,
    run_anosim,
    run_random_forest,
    run_network_analysis,
    run_correlation_analysis,
    run_pathway_analysis,
    run_functional_prediction,
    run_phylogenetic_analysis,
    run_hierarchical_clustering,run_advanced_dimred,run_source_tracking_analysis,run_cross_omics_analysis,
    run_metabolomics_analysis,
    run_sparse_cca_analysis,
    run_rda_analysis,
    run_o2pls_analysis,
)
from app.services.data_parser import parse_data_file
from app.services.orientation import (
    OrientationError,
    assert_sample_alignment,
    resolve_feature_table,
)
from app.services.rarefaction import run_rarefaction
from app.services.taxonomy_bar import run_taxonomy_bar, run_core_microbiome
from app.services.mofa import run_mofa_plus
from app.services.aldex2 import run_aldex2
from app.services.songbird import run_songbird
from app.services.enterotype import run_enterotype
from app.services.wgcna import run_wgcna
from app.services.diablo import run_diablo
from app.tasks.analysis_tasks import (
    alpha_diversity_task,
    beta_diversity_task,
    differential_task,
    pcoa_task,
    heatmap_task,
    random_forest_task,
    nmds_task,
    permanova_task,
    anosim_task,
)
from app.utils.session_manager import SessionManager

logger = logging.getLogger(__name__)
router = APIRouter()

# Session manager instance for caching
session_manager = SessionManager()

# Thresholds for async vs sync execution
ASYNC_FEATURE_THRESHOLD = 1000
ASYNC_SAMPLE_THRESHOLD = 100


# Cache the worker probe: it costs a broker round-trip and the answer rarely
# changes within a request burst.
_WORKER_PROBE: Dict[str, Any] = {'checked_at': 0.0, 'available': False}
_WORKER_PROBE_TTL = 30.0


def _workers_available() -> bool:
    """Check whether at least one Celery worker is alive and consuming.

    A reachable broker is not enough: with the SQLite broker fallback, ``.delay()``
    happily accepts a task even when nothing will ever run it, leaving the job
    stuck at 'pending' forever while the client polls. Probing for live workers
    is what actually distinguishes "will run" from "will hang".
    """
    now = time.time()
    if now - _WORKER_PROBE['checked_at'] < _WORKER_PROBE_TTL:
        return _WORKER_PROBE['available']

    available = False
    try:
        replies = celery_app.control.ping(timeout=1.0)
        available = bool(replies)
    except Exception as e:
        logger.debug(f'Celery worker probe failed: {e}')
        available = False

    _WORKER_PROBE.update({'checked_at': now, 'available': available})
    if not available:
        logger.info('No Celery worker responded; large analyses will run synchronously.')
    return available


def _should_use_async(df: pd.DataFrame) -> bool:
    """Decide whether to offload an analysis to Celery.

    Requires both a large dataset *and* a live worker -- see _workers_available.
    """
    n_features = len(df.index)
    n_samples = len(df.columns)
    is_large = n_features > ASYNC_FEATURE_THRESHOLD or n_samples > ASYNC_SAMPLE_THRESHOLD
    return is_large and _workers_available()


def _get_celery_task_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Query Celery task status by job ID."""
    try:
        result = celery_app.AsyncResult(job_id)
        if result.state == 'PENDING':
            return {'status': 'pending', 'progress': 0}
        elif result.state == 'STARTED':
            meta = result.info or {}
            return {'status': 'running', 'progress': meta.get('progress', 0), 'message': meta.get('message', '')}
        elif result.state == 'SUCCESS':
            return {'status': 'success', 'result': result.result}
        elif result.state in ('FAILURE', 'REVOKED'):
            return {'status': 'failed', 'error': str(result.info) if result.info else 'Task failed'}
        else:
            return {'status': result.state.lower(), 'progress': 0}
    except Exception as e:
        logger.warning(f"Failed to get Celery task status: {e}")
        return None

# ─────────────────────────────── Data retrieval helpers


def _orient(session_id: str, db: DBSession, df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Put a parsed feature table into canonical features x samples orientation.

    Orientation is resolved once, here, against the session's metadata -- see
    app/services/orientation.py. Analysis functions must not re-guess.
    """
    metadata_df = get_metadata_df(session_id, db)
    try:
        oriented, report = resolve_feature_table(df, metadata_df, name=name)
    except OrientationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    for w in report.warnings:
        logger.warning('Session %s: %s', session_id, w)
    _LAST_ORIENTATION[session_id] = report.to_dict()
    return oriented


# Most recent orientation decision per session, attached to analysis responses so
# the client can show how the table was interpreted.
_LAST_ORIENTATION: Dict[str, Dict[str, Any]] = {}


def get_dataframe(session_id: str, db: DBSession) -> pd.DataFrame:
    """Get the feature table as a DataFrame for a session (features x samples)."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type.in_([
            'feature_table', 'biom', 'shared', 'filtered_feature_table', 'normalized_relative',
            'microbiome', 'metabolome'
        ]))
        .order_by(DataFile.id.desc())
        .first()
    )
    if not data_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No feature table found for this session',
        )
    try:
        df, _ = parse_data_file(Path(data_file.file_path), use_chunks=True)
    except Exception as e:
        logger.error(f'Failed to parse data file: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to parse data file: {str(e)}',
        )
    return _orient(session_id, db, df, data_file.original_name or 'feature table')


def get_metadata_df(session_id: str, db: DBSession) -> Optional[pd.DataFrame]:
    """Get metadata DataFrame for a session if available."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type == 'metadata')
        .first()
    )
    if not data_file:
        return None
    try:
        # Multi-omics metadata is almost always tab-separated; try that first,
        # then fall back to comma-separated.
        try:
            df = pd.read_csv(data_file.file_path, sep='\t', index_col=0)
        except Exception:
            df = pd.read_csv(data_file.file_path, index_col=0)
        return df
    except Exception:
        return None


def get_dataframe_by_name(session_id: str, db: DBSession, name_pattern: str) -> Optional[pd.DataFrame]:
    """Get a feature table by original filename pattern (case-insensitive)."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type.in_([
            'feature_table', 'biom', 'shared', 'filtered_feature_table', 'normalized_relative',
            'microbiome', 'metabolome'
        ]))
        .filter(DataFile.original_name.ilike(f'%{name_pattern}%'))
        .order_by(DataFile.id.desc())
        .first()
    )
    if not data_file:
        return None
    try:
        df, _ = parse_data_file(Path(data_file.file_path), use_chunks=True)
    except Exception as e:
        logger.error(f'Failed to parse data file {data_file.original_name}: {e}')
        return None
    return _orient(session_id, db, df, data_file.original_name or name_pattern)


def get_dataframe_by_type(session_id: str, db: DBSession, file_type: str) -> Optional[pd.DataFrame]:
    """Get a DataFrame by exact file_type."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type == file_type)
        .order_by(DataFile.id.desc())
        .first()
    )
    if not data_file:
        return None
    try:
        df, _ = parse_data_file(Path(data_file.file_path), file_type=file_type, use_chunks=True)
    except Exception as e:
        logger.error(f'Failed to parse data file {data_file.file_path}: {e}')
        return None
    return _orient(session_id, db, df, data_file.original_name or file_type)


def get_microbiome_df(session_id: str, db: DBSession) -> Optional[pd.DataFrame]:
    """Load the microbiome feature table for a session."""
    df = get_dataframe_by_type(session_id, db, 'microbiome')
    if df is None:
        df = get_dataframe_by_type(session_id, db, 'metaphlan')
    if df is None:
        df = get_dataframe(session_id, db)
    return df


def get_metabolome_df(session_id: str, db: DBSession) -> Optional[pd.DataFrame]:
    """Load the metabolome feature table for a session."""
    df = get_dataframe_by_type(session_id, db, 'metabolome')
    if df is None:
        df = get_dataframe_by_type(session_id, db, 'humann3')
    return df


# ─────────────────────────────── Generic analysis helpers


def _guard_approximation(method_key: str, request: Any) -> Dict[str, Any]:
    """Resolve provenance for a method that may fall back to an approximation.

    Reads ``allow_approximation`` from the request (either a top-level field or
    inside ``parameters``) and turns a refusal into a 400 whose message names the
    missing R package and what the substitute actually computes.
    """
    params = getattr(request, 'parameters', None) or {}
    allow = bool(
        getattr(request, 'allow_approximation', False)
        or (params.get('allow_approximation') if isinstance(params, dict) else False)
    )
    try:
        return r_engine_for(method_key, allow)
    except ApproximationRefused as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _guard_unvalidated(method_key: str, request: Any, reason: str) -> Dict[str, Any]:
    """Block a method whose implementation is known not to match its name.

    Unlike an approximation of a published algorithm, these compute something
    that is not the named method at all -- UniFrac over a phylogeny simulated
    from taxon-name string similarity, PICRUSt2 against a toy reference table
    hard-coded in this repo. They stay reachable for development but refuse to
    run unless the caller explicitly acknowledges the limitation, and every
    result they do return is labelled.
    """
    params = getattr(request, 'parameters', None) or {}
    if not isinstance(params, dict):
        params = {}
    acknowledged = bool(
        getattr(request, 'acknowledge_unvalidated', False)
        or params.get('acknowledge_unvalidated')
    )
    if not acknowledged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{method_key}' is not available: {reason} Results from it must not "
                f"be reported as {method_key}. To run it anyway for development "
                f'purposes, resend with "acknowledge_unvalidated": true in '
                f"`parameters`."
            ),
        )
    return {
        'engine': f'unvalidated::{method_key}',
        'is_approximation': True,
        'is_validated': False,
        'approximation_note': reason,
        'reporting_guidance': (
            f'These numbers are not {method_key} output and must not be published '
            f'as such.'
        ),
    }


def _jsonify(obj: Any) -> Any:
    """Recursively convert numpy/pandas scalars and arrays to JSON-native types.

    Plotly figures and sklearn outputs carry numpy arrays and numpy scalars.
    SQLAlchemy's JSON column serialises with the stdlib encoder, which rejects
    them ("Object of type ndarray is not JSON serializable") and aborts the whole
    request at commit time. Sanitising here keeps that failure mode out of every
    endpoint.
    """
    import numpy as _np

    if isinstance(obj, dict):
        return {str(k): _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, _np.ndarray):
        return _jsonify(obj.tolist())
    if isinstance(obj, _np.generic):
        obj = obj.item()
    if isinstance(obj, float):
        # NaN/Inf are not valid JSON; null round-trips through every client.
        return None if (obj != obj or obj in (float('inf'), float('-inf'))) else obj
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    if isinstance(obj, pd.Series):
        return _jsonify(obj.to_dict())
    if isinstance(obj, pd.DataFrame):
        return _jsonify(obj.to_dict(orient='records'))
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    return str(obj)


def _save_result(session_id: str, job: AnalysisJob, result_data: Dict[str, Any]) -> Dict[str, Any]:
    """Save an analysis result to disk and update the job record.

    ``result_data`` is sanitised **in place** so that the caller's own reference
    -- which is what every endpoint hands to the Pydantic response model -- is
    JSON-safe too. Returning a new dict instead would leave 37 call sites
    serialising raw numpy and failing at response time.

    Raises:
        HTTPException: 400 if the analysis reported an error. Service functions
            signal failure by returning ``{'error': ...}``; every endpoint used
            to save that and then set ``status='completed'``, so a failed
            PERMANOVA came back as ``201 Created`` with a success status and an
            error buried in the payload. Failures are surfaced as failures here,
            in one place, for all endpoints.
    """
    if isinstance(result_data, dict) and result_data.get('error'):
        message = str(result_data['error'])
        job.status = 'failed'
        job.error_message = message
        job.completed_at = datetime.utcnow()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    session_dir = Path(settings.UPLOAD_DIR) / session_id / 'results'
    session_dir.mkdir(parents=True, exist_ok=True)
    result_path = session_dir / f'analysis_{job.id}_{job.job_type}.json'
    import json

    clean = _jsonify(result_data)
    result_data.clear()
    result_data.update(clean)

    with open(result_path, 'w') as f:
        json.dump(result_data, f, indent=2, default=str)
    job.result_path = str(result_path)
    job.result_data = result_data
    return result_data


def _submit_async_task(task_func, _session_id: str, job: AnalysisJob, **kwargs) -> AnalysisResponse:
    """Submit a Celery async task and return a pending response.

    ``kwargs`` holds the Celery task's own arguments, which include a
    ``session_id``. The session id used for the *response* is therefore named
    ``_session_id`` -- with both called ``session_id``, every call site bound the
    argument twice and raised ``TypeError: got multiple values for argument
    'session_id'`` before the body ever ran. This path was unreachable until the
    orientation fix made large datasets actually take it.
    """
    kwargs.setdefault('session_id', _session_id)
    try:
        celery_job = task_func.delay(**kwargs)
        job.parameters = {**(job.parameters or {}), 'celery_task_id': celery_job.id}
        return AnalysisResponse(
            job_id=job.id,
            session_id=_session_id,
            job_type=job.job_type,
            status='pending',
            parameters=job.parameters,
            started_at=job.started_at,
        )
    except Exception as e:
        logger.error(f'Failed to submit async task: {e}')
        raise HTTPException(status_code=500, detail=f'Failed to submit async task: {str(e)}')


# ─────────────────────────────── Job Status & Result Endpoints

@router.get(
    '/sessions/{session_id}/jobs/{job_id}/status',
    responses={404: {'model': ErrorResponse}},
)
async def get_job_status(
    session_id: str,
    job_id: int,
    db: DBSession = Depends(get_db),
):
    """Get the status of an analysis job (supports both DB and Celery tasks)."""
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).filter(AnalysisJob.session_id == session_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f'Job {job_id} not found')
    
    # Check if there's a Celery task ID
    celery_task_id = job.parameters.get('celery_task_id') if job.parameters else None
    if celery_task_id:
        celery_status = _get_celery_task_status(celery_task_id)
        if celery_status:
            # Update DB status if Celery state is more recent
            if celery_status['status'] == 'success' and job.status != 'completed':
                job.status = 'completed'
                job.result_data = celery_status.get('result')
                if isinstance(job.result_data, dict) and 'result_data' in job.result_data:
                    job.result_data = job.result_data['result_data']
                db.commit()
            elif celery_status['status'] == 'failed' and job.status != 'failed':
                job.status = 'failed'
                job.error_message = celery_status.get('error', 'Task failed')
                db.commit()
            elif celery_status['status'] == 'running' and job.status not in ('running', 'completed', 'failed'):
                job.status = 'running'
                db.commit()
            
            return {
                'job_id': job.id,
                'status': celery_status['status'],
                'progress': celery_status.get('progress', 0),
                'message': celery_status.get('message', ''),
                'celery_task_id': celery_task_id,
            }
    
    return {
        'job_id': job.id,
        'status': job.status,
        'progress': 100 if job.status == 'completed' else 0,
        'message': job.error_message if job.status == 'failed' else '',
    }


@router.get(
    '/sessions/{session_id}/jobs/{job_id}/result',
    response_model=AnalysisResultResponse,
    responses={404: {'model': ErrorResponse}},
)
async def get_job_result(
    session_id: str,
    job_id: int,
    page: int = Query(1, ge=1, description='Page number for paginated results'),
    page_size: int = Query(100, ge=1, le=1000, description='Items per page'),
    sort_by: str = Query('padj', description='Sort column'),
    sort_order: str = Query('asc', description='Sort order: asc or desc'),
    db: DBSession = Depends(get_db),
):
    """Get paginated analysis result for a completed job."""
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).filter(AnalysisJob.session_id == session_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f'Job {job_id} not found')
    
    if job.status == 'pending':
        raise HTTPException(status_code=400, detail='Job is still pending')
    if job.status == 'running':
        raise HTTPException(status_code=400, detail='Job is still running')
    if job.status == 'failed':
        raise HTTPException(status_code=500, detail=f'Job failed: {job.error_message or "Unknown error"}')
    
    result_data = job.result_data
    
    # Handle paginated differential results
    if job.job_type == 'differential' and result_data and 'all_features' in result_data:
        diff_df = pd.DataFrame(result_data['all_features'])
        if not diff_df.empty:
            engine = AnalysisEngine()
            paged = engine.get_paged_differential_results(
                diff_df, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order
            )
            result_data['paged_results'] = paged
            result_data['current_page'] = page
            result_data['page_size'] = page_size
    
    return AnalysisResultResponse(
        job_id=job.id,
        status=job.status,
        result_data=result_data,
        download_url=f'/api/v1/sessions/{session_id}/analysis/{job_id}/download' if job.result_path else None,
    )


# ─────────────────────────────── Alpha Diversity


@router.post(
    '/sessions/{session_id}/analyze/alpha-diversity',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_alpha_diversity(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Run alpha diversity analysis. Uses async (Celery) for large datasets."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    try:
        # Create job record
        job = AnalysisJob(
            session_id=session_id,
            job_type='alpha',
            parameters={
                'indices': request.parameters.get('indices', ['shannon', 'simpson', 'chao1', 'observed', 'evenness']),
                'group_column': request.group_column,
            },
            status='pending',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Check data size: use async for large datasets
        if _should_use_async(df):
            logger.info(f"Large dataset detected ({df.shape}), using async alpha-diversity task")
            job.status = 'pending'
            db.commit()
            return _submit_async_task(
                alpha_diversity_task,
                session_id, job,
                session_id=session_id,
                metrics=request.parameters.get('indices', ['shannon', 'simpson', 'chao1', 'observed', 'evenness']),
                grouping=request.group_column,
            )

        # Small dataset: synchronous execution
        job.status = 'running'
        db.commit()

        result_data = run_alpha_diversity(df, metadata_df, job.parameters)

        # Generate Plotly chart if metadata available
        if metadata_df is not None and request.group_column and request.group_column in metadata_df.columns:
            engine = AnalysisEngine()
            alpha_df = engine.alpha_diversity(df, metrics=job.parameters['indices'])
            plot_data = engine.plotly_alpha_boxplot(alpha_df, metadata_df, request.group_column, 'shannon')
            result_data['plot_data'] = plot_data

        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Alpha diversity analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Beta Diversity


@router.post(
    '/sessions/{session_id}/analyze/beta-diversity',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_beta_diversity(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Run beta diversity analysis. Uses async for large datasets."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='beta',
            parameters={
                'metric': request.parameters.get('metric', 'braycurtis'),
                'group_column': request.group_column,
            },
            status='pending',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        if _should_use_async(df):
            logger.info(f"Large dataset detected ({df.shape}), using async beta-diversity task")
            job.status = 'pending'
            db.commit()
            return _submit_async_task(
                beta_diversity_task,
                session_id, job,
                session_id=session_id,
                distance=request.parameters.get('metric', 'braycurtis'),
                grouping=request.group_column,
            )

        job.status = 'running'
        db.commit()

        result_data = run_beta_diversity(df, metadata_df, job.parameters)
        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Beta diversity analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── PCoA


@router.post(
    '/sessions/{session_id}/analyze/pcoa',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_pcoa(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Run PCoA. Uses async for large datasets."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='pcoa',
            parameters={
                'metric': request.parameters.get('metric', 'braycurtis'),
                'n_components': request.parameters.get('n_components', 3),
                'group_column': request.group_column,
            },
            status='pending',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        if _should_use_async(df):
            logger.info(f"Large dataset detected ({df.shape}), using async PCoA task")
            job.status = 'pending'
            db.commit()
            return _submit_async_task(
                pcoa_task,
                session_id, job,
                session_id=session_id,
                distance=request.parameters.get('metric', 'braycurtis'),
                grouping=request.group_column,
            )

        job.status = 'running'
        db.commit()

        result_data = run_pcoa(df, metadata_df, job.parameters)

        # Generate Plotly chart
        if metadata_df is not None and request.group_column and request.group_column in metadata_df.columns:
            engine = AnalysisEngine()
            dist_matrix = engine.beta_diversity(df, distance=job.parameters.get('metric', 'braycurtis'))
            pcoa_result = engine.pcoa(dist_matrix)
            plot_data = engine.plotly_pcoa_scatter(pcoa_result, metadata_df, request.group_column)
            result_data['plot_data'] = plot_data

        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'PCoA analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── NMDS


@router.post(
    '/sessions/{session_id}/analyze/nmds',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_nmds(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Run NMDS. Uses async for large datasets."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='nmds',
            parameters={
                'metric': request.parameters.get('metric', 'braycurtis'),
                'n_components': request.parameters.get('n_components', 2),
                'group_column': request.group_column,
            },
            status='pending',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        if _should_use_async(df):
            logger.info(f"Large dataset detected ({df.shape}), using async NMDS task")
            job.status = 'pending'
            db.commit()
            return _submit_async_task(
                nmds_task,
                session_id, job,
                session_id=session_id,
                distance=request.parameters.get('metric', 'braycurtis'),
                n_components=request.parameters.get('n_components', 2),
            )

        job.status = 'running'
        db.commit()

        result_data = run_nmds(df, metadata_df, job.parameters)
        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'NMDS analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Differential Analysis


@router.post(
    '/sessions/{session_id}/analyze/differential',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_differential(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Run differential abundance analysis. Uses async for large datasets."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    if metadata_df is None or request.group_column not in metadata_df.columns:
        raise HTTPException(status_code=400, detail='Metadata with valid group_column is required')

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='differential',
            parameters={
                'group_column': request.group_column,
                'test_method': request.parameters.get('test_method', 'mannwhitney'),
                'pvalue_threshold': request.parameters.get('pvalue_threshold', 0.05),
            },
            status='pending',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        if _should_use_async(df):
            logger.info(f"Large dataset detected ({df.shape}), using async differential task")
            job.status = 'pending'
            db.commit()
            try:
                g1, g2 = resolve_comparison_groups(
                    metadata_df, request.group_column,
                    request.comparisons, request.reference_group,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            return _submit_async_task(
                differential_task,
                session_id, job,
                session_id=session_id,
                method=request.parameters.get('test_method', 'mannwhitney'),
                group_var=request.group_column,
                group1=g1,
                group2=g2,
                p_adjust='BH',
            )

        job.status = 'running'
        db.commit()

        test_method = job.parameters['test_method']
        groups = metadata_df[request.group_column].dropna().unique()
        engine = AnalysisEngine()
        allow_approx = bool(request.parameters.get('allow_approximation', False))

        def _pairwise_groups():
            """Resolve the two groups to contrast, or fail with a 400."""
            try:
                return resolve_comparison_groups(
                    metadata_df, request.group_column,
                    request.comparisons, request.reference_group,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        def _engine(method_key: str):
            """Resolve provenance, turning a refusal into an actionable 400.

            Previously each R-backed branch was additionally gated on
            `len(groups) == 2`; with more groups the condition simply fell
            through to the generic Wilcoxon branch, so a DESeq2 request silently
            returned Wilcoxon results labelled 'DESeq2'.
            """
            try:
                return r_engine_for(method_key, allow_approx)
            except ApproximationRefused as e:
                raise HTTPException(status_code=400, detail=str(e))

        if test_method in ('deseq2', 'DESeq2'):
            provenance = _engine('deseq2')
            g1, g2 = _pairwise_groups()
            diff_df = run_deseq2(df, metadata_df, request.group_column, g1, g2)
            result_data = {
                'group_column': request.group_column,
                'group1': str(g1),
                'group2': str(g2),
                'reference_group': str(g1),
                'fold_change_direction': f'{g2} vs {g1}',
                'test_method': 'DESeq2',
                **provenance,
                'significant_features': diff_df[diff_df['padj'] < job.parameters['pvalue_threshold']].to_dict(orient='records'),
                'all_features': diff_df.to_dict(orient='records'),
            }
        elif test_method in ('edger', 'edgeR'):
            provenance = _engine('edger')
            g1, g2 = _pairwise_groups()
            diff_df = run_edger(df, metadata_df, request.group_column, g1, g2)
            result_data = {
                'group_column': request.group_column,
                'group1': str(g1),
                'group2': str(g2),
                'reference_group': str(g1),
                'fold_change_direction': f'{g2} vs {g1}',
                'test_method': 'edgeR',
                **provenance,
                'significant_features': diff_df[diff_df['FDR'] < job.parameters['pvalue_threshold']].to_dict(orient='records'),
                'all_features': diff_df.to_dict(orient='records'),
            }
        elif test_method in ('ancombc', 'ANCOM-BC'):
            provenance = _engine('ancombc')
            # Restrict to the requested contrast instead of rejecting the whole
            # request when the column has more than two levels. Checking
            # len(groups) against every level meant a 7-timepoint study could not
            # run ANCOM-BC at all, even with `comparisons` naming exactly two.
            g1, g2 = _pairwise_groups()
            pair_samples = metadata_df.index[metadata_df[request.group_column].isin([g1, g2])]
            ancom_meta = metadata_df.loc[pair_samples]
            ancom_df = df[df.columns.intersection(pair_samples)]
            zero_cut = request.parameters.get('zero_cut', 0.9)
            lib_cut = request.parameters.get('lib_cut', 0)
            struc_zero = request.parameters.get('struc_zero', True)
            p_adj_method = request.parameters.get('p_adj_method', 'BH')
            diff_df = run_ancombc(ancom_df, ancom_meta, request.group_column, zero_cut, lib_cut, struc_zero, p_adj_method)
            if 'error' in diff_df.columns:
                raise HTTPException(status_code=400, detail=str(diff_df['error'].iloc[0]))
            result_data = {
                'group_column': request.group_column,
                'group1': str(g1),
                'group2': str(g2),
                'reference_group': str(g1),
                'fold_change_direction': f'{g2} vs {g1}',
                'test_method': 'ANCOM-BC',
                **provenance,
                'zero_cut': zero_cut,
                'lib_cut': lib_cut,
                'struc_zero': struc_zero,
                'p_adj_method': p_adj_method,
                'significant_features': diff_df[diff_df['diff_abn'] == True].to_dict(orient='records') if 'diff_abn' in diff_df.columns else [],
                'all_features': diff_df.to_dict(orient='records'),
            }
            if 'lfc' in diff_df.columns and 'padj' in diff_df.columns:
                diff_df = diff_df.rename(columns={'lfc': 'log2FC'})
                plot_data = engine.plotly_volcano(diff_df)
                result_data['plot_data'] = plot_data
        elif test_method in ('maaslin3', 'MaAsLin3'):
            provenance = _engine('maaslin3')
            fixed_effects = request.parameters.get('fixed_effects', [request.group_column])
            random_effects = request.parameters.get('random_effects', None)
            normalization = request.parameters.get('normalization', 'TSS')
            transform = request.parameters.get('transform', 'LOG')
            diff_df = run_maaslin3(df, metadata_df, fixed_effects, random_effects, request.group_column, normalization, transform)
            if 'error' in diff_df.columns:
                raise HTTPException(status_code=400, detail=str(diff_df['error'].iloc[0]))
            result_data = {
                'test_method': 'MaAsLin3',
                **provenance,
                'normalization': normalization,
                'transform': transform,
                'fixed_effects': fixed_effects,
                'significant_features': diff_df[diff_df['padj'] < job.parameters['pvalue_threshold']].to_dict(orient='records') if 'padj' in diff_df.columns else [],
                'all_features': diff_df.to_dict(orient='records'),
            }
            # MaAsLin3 bar plot (coefficients per metadata variable)
            if 'coefficient' in diff_df.columns and 'metadata' in diff_df.columns:
                plot_data = engine.plotly_maaslin3_bar(diff_df)
                result_data['plot_data'] = plot_data
        elif test_method == 'lefse':
            provenance = _engine('lefse')
            job.parameters = {**job.parameters, 'comparisons': request.comparisons,
                              'reference_group': request.reference_group}
            result_data = run_differential_analysis(df, metadata_df, job.parameters)
            result_data.update(provenance)
        else:
            # Native Python tests (t-test / Mann-Whitney): no R equivalent is
            # being claimed, so they are not approximations of anything.
            job.parameters = {**job.parameters, 'comparisons': request.comparisons,
                              'reference_group': request.reference_group}
            result_data = run_differential_analysis(df, metadata_df, job.parameters)
            result_data.setdefault('engine', f"python::{result_data.get('test_method', test_method)}")
            result_data.setdefault('is_approximation', False)

        # Generate Plotly volcano chart.
        #
        # Each engine names its columns differently (log2FC / log2_fold_change /
        # log2FoldChange; pvalue / PValue). Renaming padj -> pvalue, as this did
        # previously, produced two columns called 'pvalue' for DESeq2 output
        # (which already has one) and then crashed inside plotly_volcano with
        # "Cannot set a DataFrame with multiple columns to the single column
        # neg_log10_p". Columns are mapped explicitly instead, and the raw
        # p-value is preferred over the adjusted one for the y-axis.
        engine = AnalysisEngine()
        if 'all_features' in result_data:
            diff_df = pd.DataFrame(result_data['all_features'])
            fc_col = next(
                (c for c in ('log2FC', 'log2_fold_change', 'log2FoldChange', 'logFC', 'lfc')
                 if c in diff_df.columns),
                None,
            )
            p_col = next(
                (c for c in ('pvalue', 'PValue', 'p_value', 'padj', 'FDR', 'qvalue')
                 if c in diff_df.columns),
                None,
            )
            if len(diff_df) > 0 and fc_col and p_col:
                volcano_df = pd.DataFrame({
                    'feature': diff_df.get('feature', pd.Series(diff_df.index, index=diff_df.index)),
                    'log2FC': pd.to_numeric(diff_df[fc_col], errors='coerce'),
                    'pvalue': pd.to_numeric(diff_df[p_col], errors='coerce'),
                }).dropna(subset=['log2FC', 'pvalue'])
                if len(volcano_df) > 0:
                    result_data['plot_data'] = engine.plotly_volcano(volcano_df)
                    result_data['volcano_pvalue_column'] = p_col

        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Differential analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── PERMANOVA


@router.post(
    '/sessions/{session_id}/analyze/permanova',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_permanova(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Run PERMANOVA. Uses async for large datasets."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    if metadata_df is None or request.group_column not in metadata_df.columns:
        raise HTTPException(status_code=400, detail='Metadata with valid group_column is required')

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='permanova',
            parameters={
                'metric': request.parameters.get('metric', 'braycurtis'),
                'group_column': request.group_column,
                'n_permutations': request.parameters.get('n_permutations', 999),
            },
            status='pending',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        if _should_use_async(df):
            logger.info(f"Large dataset detected ({df.shape}), using async PERMANOVA task")
            job.status = 'pending'
            db.commit()
            return _submit_async_task(
                permanova_task,
                session_id, job,
                session_id=session_id,
                distance=request.parameters.get('metric', 'braycurtis'),
                group_var=request.group_column,
                n_permutations=request.parameters.get('n_permutations', 999),
            )

        job.status = 'running'
        db.commit()

        result_data = run_permanova(df, metadata_df, job.parameters)
        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'PERMANOVA analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── ANOSIM


@router.post(
    '/sessions/{session_id}/analyze/anosim',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_anosim(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Run ANOSIM. Uses async for large datasets."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    if metadata_df is None or request.group_column not in metadata_df.columns:
        raise HTTPException(status_code=400, detail='Metadata with valid group_column is required')

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='anosim',
            parameters={
                'metric': request.parameters.get('metric', 'braycurtis'),
                'group_column': request.group_column,
                'n_permutations': request.parameters.get('n_permutations', 999),
            },
            status='pending',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        if _should_use_async(df):
            logger.info(f"Large dataset detected ({df.shape}), using async ANOSIM task")
            job.status = 'pending'
            db.commit()
            return _submit_async_task(
                anosim_task,
                session_id, job,
                session_id=session_id,
                distance=request.parameters.get('metric', 'braycurtis'),
                group_var=request.group_column,
                n_permutations=request.parameters.get('n_permutations', 999),
            )

        job.status = 'running'
        db.commit()

        result_data = run_anosim(df, metadata_df, job.parameters)
        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'ANOSIM analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Random Forest


@router.post(
    '/sessions/{session_id}/analyze/random-forest',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_random_forest(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Run Random Forest. Uses async for large datasets."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    if metadata_df is None or request.group_column not in metadata_df.columns:
        raise HTTPException(status_code=400, detail='Metadata with valid group_column is required')

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='random_forest',
            parameters={
                'group_column': request.group_column,
                'n_estimators': request.parameters.get('n_estimators', 500),
            },
            status='pending',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        if _should_use_async(df):
            logger.info(f"Large dataset detected ({df.shape}), using async Random Forest task")
            job.status = 'pending'
            db.commit()
            return _submit_async_task(
                random_forest_task,
                session_id, job,
                session_id=session_id,
                group_var=request.group_column,
                n_estimators=request.parameters.get('n_estimators', 500),
            )

        job.status = 'running'
        db.commit()

        result_data = run_random_forest(df, metadata_df, job.parameters)

        # Add feature importance chart
        engine = AnalysisEngine()
        if 'feature_importance' in result_data:
            fi_df = pd.DataFrame(result_data['feature_importance'])
            plot_data = engine.plotly_rf_feature_importance(fi_df, top_n=20)
            result_data['plot_data'] = plot_data

        # Add confusion matrix chart (if multi-class)
        if 'confusion_matrix' in result_data:
            cm_data = result_data['confusion_matrix']
            plot_data_cm = engine.plotly_confusion_matrix(cm_data)
            result_data['confusion_matrix_plot'] = plot_data_cm

        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Random Forest analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── LEfSe


@router.post(
    '/sessions/{session_id}/analyze/lefse',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_lefse(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Run LEfSe (Linear Discriminant Analysis Effect Size) biomarker discovery."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    if metadata_df is None or request.group_column not in metadata_df.columns:
        raise HTTPException(status_code=400, detail='Metadata with valid group_column is required')

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='lefse',
            parameters={
                'group_column': request.group_column,
                'lda_threshold': request.parameters.get('lda_threshold', 2.0),
                'test_method': 'lefse',
            },
            status='pending',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        job.status = 'running'
        db.commit()

        result_data = run_differential_analysis(df, metadata_df, job.parameters)
        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'LEfSe analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Heatmap


@router.post(
    '/sessions/{session_id}/analyze/heatmap',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_heatmap(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Generate heatmap. Uses async for large datasets."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='heatmap',
            parameters={
                'top_n': request.parameters.get('top_n', 50),
                'cluster_rows': request.parameters.get('cluster_rows', True),
                'cluster_cols': request.parameters.get('cluster_cols', True),
                'normalize': request.parameters.get('normalize', 'zscore'),
                'group_column': request.group_column,
            },
            status='pending',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        if _should_use_async(df):
            logger.info(f"Large dataset detected ({df.shape}), using async heatmap task")
            job.status = 'pending'
            db.commit()
            return _submit_async_task(
                heatmap_task,
                session_id, job,
                session_id=session_id,
                n_top=request.parameters.get('top_n', 50),
            )

        job.status = 'running'
        db.commit()

        result_data = run_heatmap(df, metadata_df, job.parameters)

        # Generate Plotly heatmap
        engine = AnalysisEngine()
        plot_data = engine.plotly_heatmap(df, metadata_df, request.group_column)
        result_data['plot_data'] = plot_data

        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Heatmap generation failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')



# ─────────────────────────────── Stacked Bar


@router.post(
    '/sessions/{session_id}/analyze/stacked-bar',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_stacked_bar(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Generate stacked bar chart (compositional plot) with Plotly JSON output."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='stacked_bar',
            parameters={
                'group_column': request.group_column,
                'tax_level': request.parameters.get('tax_level'),
            },
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Generate Plotly stacked bar
        engine = AnalysisEngine()
        plot_data = engine.plotly_stacked_bar(df, metadata_df, request.group_column)
        result_data = {'plot_data': plot_data}

        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Stacked bar generation failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Library Size


@router.post(
    '/sessions/{session_id}/analyze/library-size',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_library_size(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Generate library size bar chart with Plotly JSON output."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='library_size',
            parameters={},
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        engine = AnalysisEngine()
        plot_data = engine.plotly_library_size(df)
        result_data = {'plot_data': plot_data}

        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=result_data,
            completed_at=job.completed_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Library size analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Legacy job creation / result / run endpoints


@router.post(
    '/sessions/{session_id}/analysis',
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def create_analysis(
    session_id: str,
    request: AnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Submit a generic analysis job (legacy, for queue-based processing)."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type=request.analysis_type,
            parameters={
                **request.parameters,
                'group_column': request.group_column,
                'comparisons': request.comparisons,
            },
            status='pending',
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            parameters=job.parameters,
            created_at=job.created_at,
        )
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Failed to create analysis job: {str(e)}')


@router.get(
    '/sessions/{session_id}/analysis/{job_id}',
    response_model=AnalysisResultResponse,
    responses={404: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def get_analysis_result(
    session_id: str,
    job_id: int,
    db: DBSession = Depends(get_db),
):
    """Get analysis result for a job."""
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).filter(AnalysisJob.session_id == session_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f'Analysis job {job_id} not found')

    return AnalysisResultResponse(
        job_id=job.id,
        status=job.status,
        result_data=job.result_data,
        download_url=f'/api/v1/sessions/{session_id}/analysis/{job_id}/download' if job.result_path else None,
    )


@router.post(
    '/sessions/{session_id}/analysis/{job_id}/run',
    response_model=AnalysisResponse,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def run_analysis(
    session_id: str,
    job_id: int,
    db: DBSession = Depends(get_db),
):
    """Run a pending analysis job (legacy execution path)."""
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).filter(AnalysisJob.session_id == session_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f'Analysis job {job_id} not found')

    if job.status not in ('pending', 'failed'):
        raise HTTPException(status_code=400, detail=f'Analysis job is already {job.status}')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    try:
        job.status = 'running'
        job.started_at = datetime.utcnow()
        db.commit()

        result_data = None
        if job.job_type == 'alpha':
            result_data = run_alpha_diversity(df, metadata_df, job.parameters)
        elif job.job_type == 'beta':
            result_data = run_beta_diversity(df, metadata_df, job.parameters)
        elif job.job_type == 'differential':
            result_data = run_differential_analysis(df, metadata_df, job.parameters)
        elif job.job_type == 'pcoa':
            result_data = run_pcoa(df, metadata_df, job.parameters)
        elif job.job_type == 'nmds':
            result_data = run_nmds(df, metadata_df, job.parameters)
        elif job.job_type == 'heatmap':
            result_data = run_heatmap(df, metadata_df, job.parameters)
        elif job.job_type == 'permanova':
            result_data = run_permanova(df, metadata_df, job.parameters)
        elif job.job_type == 'anosim':
            result_data = run_anosim(df, metadata_df, job.parameters)
        elif job.job_type == 'lefse':
            result_data = run_differential_analysis(df, metadata_df, job.parameters)
        elif job.job_type == 'random_forest':
            result_data = run_random_forest(df, metadata_df, job.parameters)
        elif job.job_type == 'network':
            result_data = run_network_analysis(df, metadata_df, job.parameters)
        elif job.job_type == 'correlation':
            result_data = run_correlation_analysis(df, metadata_df, job.parameters)
        elif job.job_type == 'pathway':
            result_data = run_pathway_analysis(df, parameters=job.parameters)
        elif job.job_type == 'metabolomics':
            result_data = run_metabolomics_analysis(df, metadata_df, job.parameters)
        elif job.job_type == 'sparse_cca':
            result_data = run_sparse_cca_analysis(df, None, metadata_df, job.parameters)
        elif job.job_type == 'rda':
            result_data = run_rda_analysis(df, None, metadata_df, job.parameters)
        elif job.job_type == 'o2pls':
            result_data = run_o2pls_analysis(df, None, metadata_df, job.parameters)
        else:
            raise ValueError(f'Unknown analysis type: {job.job_type}')

        _save_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return AnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            job_type=job.job_type,
            status=job.status,
            result_data=job.result_data,
            completed_at=job.completed_at,
        )
    except Exception as e:
        job.status = 'failed'
        job.error_message = str(e)
        db.commit()
        logger.error(f'Analysis job {job_id} failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Network Analysis

class NetworkAnalysisRequest(BaseModel):
    method: str = 'sparcc'
    threshold: float = 0.3
    pvalue_threshold: float = 0.05
    n_permutations: int = 100
    top_n_features: int = 150


@router.post('/sessions/{session_id}/analyze/network', response_model=AnalysisResponse)
def network_analysis(
    session_id: str,
    request: NetworkAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='network',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_network_analysis(df, parameters=request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Correlation Analysis

class CorrelationAnalysisRequest(BaseModel):
    target: str = 'feature'
    method: str = 'spearman'
    threshold: float = 0.3
    pvalue_threshold: float = 0.05
    group_column: Optional[str] = None


@router.post('/sessions/{session_id}/analyze/correlation', response_model=AnalysisResponse)
def correlation_analysis(
    session_id: str,
    request: CorrelationAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='correlation',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_correlation_analysis(df, metadata_df, request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Pathway / Functional Analysis

class PathwayAnalysisRequest(BaseModel):
    method: str = 'hypergeometric'
    pvalue_threshold: float = 0.05
    min_count: int = 10
    group_column: Optional[str] = None


@router.post('/sessions/{session_id}/analyze/pathway', response_model=AnalysisResponse)
def pathway_analysis(
    session_id: str,
    request: PathwayAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='pathway',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_pathway_analysis(df, parameters=request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Functional Prediction (PICRUSt2 / Tax4Fun)

class FunctionalPredictionRequest(BaseModel):
    method: str = 'picrust2'
    normalization: str = 'copy_number'
    ko_normalization: str = 'relabund'
    aggregation: str = 'sum'
    group_column: Optional[str] = None
    diff_test: str = 'wilcoxon'
    top_n_ko: int = 50
    top_n_pathway: int = 20
    do_differential: bool = True


@router.post('/sessions/{session_id}/analyze/functional-prediction', response_model=AnalysisResponse)
def functional_prediction(
    session_id: str,
    request: FunctionalPredictionRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='functional_prediction',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    provenance = _guard_unvalidated(
        'PICRUSt2/Tax4Fun', request,
        'the KO reference database is a small mock table hard-coded in '
        'app/services/functional_prediction.py, not the PICRUSt2 reference data.',
    )
    result_data = run_functional_prediction(df, metadata_df, request.model_dump())
    result_data.update(provenance)
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Phylogenetic Analysis (UniFrac + Faith's PD + NMDS)

class PhylogeneticAnalysisRequest(BaseModel):
    weighted: bool = True
    group_column: Optional[str] = None
    n_permutations: int = 999
    nmds_components: int = 2


@router.post('/sessions/{session_id}/analyze/phylogenetic', response_model=AnalysisResponse)
def phylogenetic_analysis(
    session_id: str,
    request: PhylogeneticAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='phylogenetic',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    provenance = _guard_unvalidated(
        'UniFrac/Faith PD', request,
        'the phylogenetic distances are simulated from taxonomic name string '
        'similarity plus random noise (see _simulate_phylogenetic_tree in '
        'app/services/phylogenetic_analysis.py), not read from a real tree.',
    )
    result_data = run_phylogenetic_analysis(df, metadata_df, request.model_dump())
    result_data.update(provenance)
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Hierarchical Clustering + Heat Tree

class HierarchicalClusteringRequest(BaseModel):
    cluster_axis: str = 'both'
    distance_metric: str = 'braycurtis'
    linkage_method: str = 'ward'
    n_clusters: int = 3
    top_n_features: int = 50
    group_column: Optional[str] = None
    compute_silhouette: bool = True


@router.post('/sessions/{session_id}/analyze/hierarchical-clustering', response_model=AnalysisResponse)
def hierarchical_clustering(
    session_id: str,
    request: HierarchicalClusteringRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='hierarchical_clustering',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_hierarchical_clustering(df, metadata_df, request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Metabolomics Analysis (PCA / Alpha / Markers)

class MetabolomicsRequest(BaseModel):
    analysis_type: str = 'pca'
    group_column: Optional[str] = 'Visit'
    reference_group: str = 'T4'
    n_components: int = 10
    transformation: str = 'zscore'
    test_method: str = 'welch'
    pvalue_threshold: float = 0.05
    fc_threshold: float = 1.5


@router.post('/sessions/{session_id}/analyze/metabolomics', response_model=AnalysisResponse)
def metabolomics_analysis(
    session_id: str,
    request: MetabolomicsRequest,
    db: DBSession = Depends(get_db),
):
    """Single-omics metabolomics analysis endpoint used by the MultiOmics page."""
    metabolome_df = get_metabolome_df(session_id, db)
    if metabolome_df is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No metabolome data found for this session',
        )
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='metabolomics',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_metabolomics_analysis(
        metabolome_df.T,
        metadata_df,
        request.model_dump(),
    )
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Cross-omics Analysis (Procrustes + Mantel)

class CrossOmicsRequest(BaseModel):
    analysis_type: str = 'both'  # 'procrustes', 'mantel', or 'both'
    procrustes_method: str = 'pcoa'
    mantel_metric: str = 'braycurtis'
    mantel_method: str = 'pearson'
    n_permutations: int = 999
    group_column: Optional[str] = None


@router.post('/sessions/{session_id}/analyze/cross-omics', response_model=AnalysisResponse)
def cross_omics_analysis(
    session_id: str,
    request: CrossOmicsRequest,
    db: DBSession = Depends(get_db),
):
    microbiome_df = get_microbiome_df(session_id, db)
    metabolome_df = get_metabolome_df(session_id, db)
    if microbiome_df is None or metabolome_df is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Cross-omics analysis requires both microbiome and metabolome data for this session',
        )
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='cross_omics',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_cross_omics_analysis(
        microbiome_df,
        metabolome_df,
        metadata_df,
        request.model_dump(),
    )
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Advanced Dimensionality Reduction (t-SNE / UMAP / MaAsLin3)

class AdvancedDimredRequest(BaseModel):
    method: str = 'both'
    tsne_perplexity: float = 30.0
    tsne_learning_rate: float = 200.0
    umap_n_neighbors: int = 15
    umap_min_dist: float = 0.1
    group_column: Optional[str] = None
    run_maaslin: bool = True
    fixed_effects: list = []
    random_effects: Optional[list] = None
    min_abundance: float = 0.0
    min_prevalence: float = 0.0


@router.post('/sessions/{session_id}/analyze/advanced-dimred', response_model=AnalysisResponse)
def advanced_dimred(
    session_id: str,
    request: AdvancedDimredRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='advanced_dimred',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_advanced_dimred(df, metadata_df, request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Source Tracking (FEAST-style)

class SourceTrackingRequest(BaseModel):
    sink_samples: list = []
    source_samples: list = []
    source_column: str = 'source_type'
    method: str = 'nnls'


@router.post('/sessions/{session_id}/analyze/source-tracking', response_model=AnalysisResponse)
def source_tracking(
    session_id: str,
    request: SourceTrackingRequest,
    db: DBSession = Depends(get_db),
):
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='source_tracking',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_source_tracking_analysis(df, metadata_df, request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Metabolomics Analysis

class MetabolomicsAnalysisRequest(BaseModel):
    analysis_type: str = 'all'  # 'pca', 'alpha_diversity', 'marker_discovery', 'all'
    group_column: Optional[str] = None
    reference_group: str = 'T4'  # Day 0 / baseline for marker discovery
    n_components: int = 10
    transformation: str = 'zscore'
    test_method: str = 'welch'
    pvalue_threshold: float = 0.05
    fc_threshold: float = 1.5


@router.post('/sessions/{session_id}/analyze/metabolomics', response_model=AnalysisResponse)
def metabolomics_analysis(
    session_id: str,
    request: MetabolomicsAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Metabolomics statistical analysis: PCA, alpha diversity, marker discovery."""
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='metabolomics',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    result_data = run_metabolomics_analysis(df, metadata_df, request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── Sparse CCA

class SparseCCARequest(BaseModel):
    n_components: int = 2
    sparsity_x: float = 0.3
    sparsity_y: float = 0.3
    n_permutations: int = 999
    group_column: Optional[str] = None


@router.post('/sessions/{session_id}/analyze/sparse-cca', response_model=AnalysisResponse)
def sparse_cca_analysis(
    session_id: str,
    request: SparseCCARequest,
    db: DBSession = Depends(get_db),
):
    """Sparse Canonical Correlation Analysis for microbiome × metabolome integration."""
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    # For sparse CCA, we need both microbiome and metabolome data.
    # In a real setup, these would be two separate files; here we reuse the
    # same feature table as microbiome and transpose a second table if available.
    job = AnalysisJob(
        session_id=session_id,
        job_type='sparse_cca',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    microbiome_df = get_microbiome_df(session_id, db)
    metabolome_df = get_metabolome_df(session_id, db)
    if microbiome_df is None or metabolome_df is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Sparse CCA requires both microbiome and metabolome data for this session',
        )
    result_data = run_sparse_cca_analysis(microbiome_df.T, metabolome_df.T, metadata_df, request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── RDA (Redundancy Analysis)

class RDARequest(BaseModel):
    n_components: int = 2
    test_permutation: bool = True
    n_permutations: int = 999
    group_column: Optional[str] = None


@router.post('/sessions/{session_id}/analyze/rda', response_model=AnalysisResponse)
def rda_analysis(
    session_id: str,
    request: RDARequest,
    db: DBSession = Depends(get_db),
):
    """Redundancy Analysis: model metabolome as function of microbiome."""
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='rda',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    microbiome_df = get_microbiome_df(session_id, db)
    metabolome_df = get_metabolome_df(session_id, db)
    if microbiome_df is None or metabolome_df is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='RDA requires both microbiome and metabolome data for this session',
        )
    result_data = run_rda_analysis(microbiome_df.T, metabolome_df.T, metadata_df, request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ─────────────────────────────── O2PLS

class O2PLSRequest(BaseModel):
    n_joint: int = 2
    n_ortho_x: int = 1
    n_ortho_y: int = 1
    group_column: Optional[str] = None


@router.post('/sessions/{session_id}/analyze/o2pls', response_model=AnalysisResponse)
def o2pls_analysis(
    session_id: str,
    request: O2PLSRequest,
    db: DBSession = Depends(get_db),
):
    """Two-way Orthogonal PLS for multi-omics integration."""
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='o2pls',
        parameters=request.model_dump(),
        status='pending',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    microbiome_df = get_microbiome_df(session_id, db)
    metabolome_df = get_metabolome_df(session_id, db)
    if microbiome_df is None or metabolome_df is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='O2PLS requires both microbiome and metabolome data for this session',
        )
    result_data = run_o2pls_analysis(microbiome_df.T, metabolome_df.T, metadata_df, request.model_dump())
    _save_result(session_id, job, result_data)
    job.status = 'completed'
    job.completed_at = datetime.utcnow()
    db.commit()
    return AnalysisResponse(
        job_id=job.id,
        session_id=session_id,
        job_type=job.job_type,
        status=job.status,
        result_data=job.result_data,
        completed_at=job.completed_at,
    )


# ───────────────────────────────────────────────────────────────
# P0: Rarefaction, Taxonomy Bar, Core Microbiome
# ───────────────────────────────────────────────────────────────

class RarefactionRequest(BaseModel):
    group_column: Optional[str] = None
    metrics: Optional[list] = None
    max_depth: Optional[int] = None
    steps: int = 20
    iterations: int = 10


@router.post('/sessions/{session_id}/analyze/rarefaction', response_model=AnalysisResponse)
async def analyze_rarefaction(session_id: str, request: RarefactionRequest, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='rarefaction',
        parameters=request.model_dump(),
        status='running',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        # run_rarefaction works sample-wise (its `df` is samples x taxa), while
        # get_dataframe returns the canonical features x samples orientation.
        result = run_rarefaction(df.T, metadata_df, group_column=request.group_column, metrics=request.metrics, max_depth=request.max_depth, steps=request.steps, iterations=request.iterations)
        _save_result(session_id, job, result)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()
        return AnalysisResponse(job_id=job.id, session_id=session_id, job_type=job.job_type, status=job.status, result_data=job.result_data, completed_at=job.completed_at)
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')
class TaxonomyBarRequest(BaseModel):
    group_column: Optional[str] = None
    tax_level: str = 'genus'
    top_n: int = 15


@router.post('/sessions/{session_id}/analyze/taxonomy-bar', response_model=AnalysisResponse)
async def analyze_taxonomy_bar(session_id: str, request: TaxonomyBarRequest, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='taxonomy_bar',
        parameters=request.model_dump(),
        status='running',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        result = run_taxonomy_bar(df, metadata_df, group_column=request.group_column, tax_level=request.tax_level, top_n=request.top_n)
        _save_result(session_id, job, result)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()
        return AnalysisResponse(job_id=job.id, session_id=session_id, job_type=job.job_type, status=job.status, result_data=job.result_data, completed_at=job.completed_at)
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')
class CoreMicrobiomeRequest(BaseModel):
    group_column: Optional[str] = None
    prevalence_threshold: float = 0.5
    abundance_threshold: float = 0.01


@router.post('/sessions/{session_id}/analyze/core-microbiome', response_model=AnalysisResponse)
async def analyze_core_microbiome(session_id: str, request: CoreMicrobiomeRequest, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='core_microbiome',
        parameters=request.model_dump(),
        status='running',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        result = run_core_microbiome(df, metadata_df, group_column=request.group_column, prevalence_threshold=request.prevalence_threshold, abundance_threshold=request.abundance_threshold)
        _save_result(session_id, job, result)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()
        return AnalysisResponse(job_id=job.id, session_id=session_id, job_type=job.job_type, status=job.status, result_data=job.result_data, completed_at=job.completed_at)
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')
class MOFARequest(BaseModel):
    n_factors: int = 5
    group_column: Optional[str] = None


@router.post('/sessions/{session_id}/analyze/mofa', response_model=AnalysisResponse)
async def analyze_mofa(session_id: str, request: MOFARequest, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')
    mb_df = get_microbiome_df(session_id, db)
    met_df = get_metabolome_df(session_id, db)
    if mb_df is None or met_df is None:
        raise HTTPException(status_code=400, detail='Both microbiome and metabolome data required for MOFA+')
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='mofa',
        parameters=request.model_dump(),
        status='running',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        # get_*_df returns the canonical features x samples orientation;
        # this service works sample-wise (its `df` is samples x features).
        result = run_mofa_plus(mb_df.T, met_df.T, metadata_df, n_factors=request.n_factors, group_column=request.group_column)
        _save_result(session_id, job, result)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()
        return AnalysisResponse(job_id=job.id, session_id=session_id, job_type=job.job_type, status=job.status, result_data=job.result_data, completed_at=job.completed_at)
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'MOFA+ analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


class ALDEx2Request(BaseModel):
    group_column: str
    test_method: str = 'welch'
    # Accepted for consistency with AnalysisRequest: options may be sent either
    # as top-level fields or inside `parameters` (both are read by the route).
    parameters: Dict[str, Any] = Field(default_factory=dict)
    # Read by _guard_approximation; without it the opt-in could never be sent
    # for endpoints that use a typed model instead of the generic AnalysisRequest.
    allow_approximation: bool = False


@router.post('/sessions/{session_id}/analyze/aldex2', response_model=AnalysisResponse)
async def analyze_aldex2(session_id: str, request: ALDEx2Request, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    if metadata_df is None or request.group_column not in metadata_df.columns:
        raise HTTPException(status_code=400, detail='Metadata with valid group_column required')
    job = AnalysisJob(
        session_id=session_id,
        job_type='aldex2',
        parameters=request.model_dump(),
        status='running',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        provenance = _guard_approximation('aldex2', request)
        # run_aldex2 documents samples x features; get_dataframe returns the
        # canonical features x samples.
        result = run_aldex2(df.T, metadata_df, group_column=request.group_column, test_method=request.test_method)
        result.update(provenance)
        _save_result(session_id, job, result)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()
        return AnalysisResponse(job_id=job.id, session_id=session_id, job_type=job.job_type, status=job.status, result_data=job.result_data, completed_at=job.completed_at)
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'ALDEx2 analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


class SongbirdRequest(BaseModel):
    group_column: str
    epochs: int = 1000


@router.post('/sessions/{session_id}/analyze/songbird', response_model=AnalysisResponse)
async def analyze_songbird(session_id: str, request: SongbirdRequest, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    if metadata_df is None or request.group_column not in metadata_df.columns:
        raise HTTPException(status_code=400, detail='Metadata with valid group_column required')
    job = AnalysisJob(
        session_id=session_id,
        job_type='songbird',
        parameters=request.model_dump(),
        status='running',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        # get_*_df returns the canonical features x samples orientation;
        # this service works sample-wise (its `df` is samples x features).
        result = run_songbird(df.T, metadata_df, group_column=request.group_column, epochs=request.epochs)
        _save_result(session_id, job, result)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()
        return AnalysisResponse(job_id=job.id, session_id=session_id, job_type=job.job_type, status=job.status, result_data=job.result_data, completed_at=job.completed_at)
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Songbird analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


class EnterotypeRequest(BaseModel):
    n_clusters: int = 3
    # Abundance-weighted by default. 'jaccard' is presence/absence, and on a
    # typical genus table every sample carries every genus, so all distances
    # collapse to 0 and no enterotypes can be found.
    distance_metric: str = 'braycurtis'
    group_column: Optional[str] = None
    # Accepted for consistency with AnalysisRequest: options may be sent either
    # as top-level fields or inside `parameters` (both are read by the route).
    parameters: Dict[str, Any] = Field(default_factory=dict)



@router.post('/sessions/{session_id}/analyze/enterotype', response_model=AnalysisResponse)
async def analyze_enterotype(session_id: str, request: EnterotypeRequest, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='enterotype',
        parameters=request.model_dump(),
        status='running',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        # get_*_df returns the canonical features x samples orientation;
        # this service works sample-wise (its `df` is samples x features).
        # Options may arrive top-level or inside `parameters`; prefer an explicit
        # value in `parameters` so both request styles behave the same.
        n_clusters = request.parameters.get('n_clusters', request.n_clusters)
        distance_metric = request.parameters.get('distance_metric', request.distance_metric)
        result = run_enterotype(df.T, metadata_df, n_clusters=n_clusters, distance_metric=distance_metric)
        _save_result(session_id, job, result)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()
        return AnalysisResponse(job_id=job.id, session_id=session_id, job_type=job.job_type, status=job.status, result_data=job.result_data, completed_at=job.completed_at)
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'Enterotype analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


class WGCNARequest(BaseModel):
    power: int = 6
    min_module_size: int = 10
    merge_cut_height: float = 0.25
    group_column: Optional[str] = None
    # Accepted for consistency with AnalysisRequest: options may be sent either
    # as top-level fields or inside `parameters` (both are read by the route).
    parameters: Dict[str, Any] = Field(default_factory=dict)
    allow_approximation: bool = False


@router.post('/sessions/{session_id}/analyze/wgcna', response_model=AnalysisResponse)
async def analyze_wgcna(session_id: str, request: WGCNARequest, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')
    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)
    job = AnalysisJob(
        session_id=session_id,
        job_type='wgcna',
        parameters=request.model_dump(),
        status='running',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        provenance = _guard_approximation('wgcna', request)
        result = run_wgcna(df, metadata_df, power=request.power, min_module_size=request.min_module_size, merge_cut_height=request.merge_cut_height)
        result.update(provenance)
        _save_result(session_id, job, result)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()
        return AnalysisResponse(job_id=job.id, session_id=session_id, job_type=job.job_type, status=job.status, result_data=job.result_data, completed_at=job.completed_at)
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'WGCNA analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


class DIABLORequest(BaseModel):
    n_components: int = 2
    group_column: str
    # Accepted for consistency with AnalysisRequest: options may be sent either
    # as top-level fields or inside `parameters` (both are read by the route).
    parameters: Dict[str, Any] = Field(default_factory=dict)
    allow_approximation: bool = False


@router.post('/sessions/{session_id}/analyze/diablo', response_model=AnalysisResponse)
async def analyze_diablo(session_id: str, request: DIABLORequest, db: DBSession = Depends(get_db)):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')
    mb_df = get_microbiome_df(session_id, db)
    met_df = get_metabolome_df(session_id, db)
    if mb_df is None or met_df is None:
        raise HTTPException(status_code=400, detail='Both microbiome and metabolome data required for DIABLO')
    metadata_df = get_metadata_df(session_id, db)
    if metadata_df is None or request.group_column not in metadata_df.columns:
        raise HTTPException(status_code=400, detail='Metadata with valid group_column required')
    job = AnalysisJob(
        session_id=session_id,
        job_type='diablo',
        parameters=request.model_dump(),
        status='running',
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        provenance = _guard_approximation('diablo', request)
        result = run_diablo(mb_df, met_df, metadata_df, group_column=request.group_column, n_components=request.n_components)
        result.update(provenance)
        _save_result(session_id, job, result)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()
        return AnalysisResponse(job_id=job.id, session_id=session_id, job_type=job.job_type, status=job.status, result_data=job.result_data, completed_at=job.completed_at)
    except HTTPException:
        # Deliberate 4xx from inside the try block: keep its status code.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f'DIABLO analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')
