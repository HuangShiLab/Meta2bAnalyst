"""
Meta2bAnalyst - Analysis API Routes (Alpha/Beta/Differential/PCoA/NMDS/Heatmap/StackedBar/RF/PERMANOVA/ANOSIM)
Provides direct endpoints for each analysis type with Plotly JSON output.
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import AnalysisJob, DataFile, Session as SessionModel
from app.schemas import AnalysisRequest, AnalysisResponse, AnalysisResultResponse, ErrorResponse
from app.services.analysis_engine import (
    AnalysisEngine,
    run_alpha_diversity,
    run_beta_diversity,
    run_differential_analysis,
    run_pcoa,
    run_nmds,
    run_heatmap,
    run_permanova,
    run_anosim,
    run_random_forest,
)
from app.services.data_parser import parse_data_file

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────── Data retrieval helpers


def get_dataframe(session_id: str, db: DBSession) -> pd.DataFrame:
    """Get the feature table as a DataFrame for a session."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type.in_([
            'feature_table', 'biom', 'shared', 'filtered_feature_table', 'normalized_relative'
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
        df, _ = parse_data_file(Path(data_file.file_path))
        return df
    except Exception as e:
        logger.error(f'Failed to parse data file: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to parse data file: {str(e)}',
        )


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
        df = pd.read_csv(data_file.file_path, sep='\t', index_col=0)
        return df
    except Exception:
        return None


# ─────────────────────────────── Generic analysis helpers


def _save_result(session_id: str, job: AnalysisJob, result_data: Dict[str, Any]) -> None:
    """Save analysis result to disk and update job record."""
    session_dir = Path('./uploads') / session_id / 'results'
    session_dir.mkdir(parents=True, exist_ok=True)
    result_path = session_dir / f'analysis_{job.id}_{job.job_type}.json'
    import json
    with open(result_path, 'w') as f:
        json.dump(result_data, f, indent=2, default=str)
    job.result_path = str(result_path)
    job.result_data = result_data


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
    """Run alpha diversity analysis and return Plotly boxplot data."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    try:
        # Create job
        job = AnalysisJob(
            session_id=session_id,
            job_type='alpha',
            parameters={
                'indices': request.parameters.get('indices', ['shannon', 'simpson', 'chao1', 'observed', 'evenness']),
                'group_column': request.group_column,
            },
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Run analysis
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
    """Run beta diversity analysis and return distance matrix data."""
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
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

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
    """Run PCoA and return Plotly scatter plot data."""
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
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

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
    """Run NMDS and return coordinate data."""
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
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

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
    """Run differential abundance analysis and return Plotly volcano plot data."""
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
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        result_data = run_differential_analysis(df, metadata_df, job.parameters)

        # Generate Plotly volcano chart
        engine = AnalysisEngine()
        groups = metadata_df[request.group_column].dropna().unique()
        if len(groups) == 2 and 'all_features' in result_data:
            diff_df = pd.DataFrame(result_data['all_features'])
            if len(diff_df) > 0 and 'pvalue' in diff_df.columns and 'log2_fold_change' in diff_df.columns:
                # Rename column to match engine expectation
                diff_df = diff_df.rename(columns={'log2_fold_change': 'log2FC'})
                plot_data = engine.plotly_volcano(diff_df)
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
    """Run PERMANOVA statistical test."""
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
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

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
    """Run ANOSIM statistical test."""
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
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

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
    """Run Random Forest classification and feature importance analysis."""
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
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        result_data = run_random_forest(df, metadata_df, job.parameters)
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
    except Exception as e:
        db.rollback()
        logger.error(f'Random Forest analysis failed: {e}')
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
    """Generate heatmap with Plotly JSON output."""
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
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

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
        elif job.job_type == 'random_forest':
            result_data = run_random_forest(df, metadata_df, job.parameters)
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
