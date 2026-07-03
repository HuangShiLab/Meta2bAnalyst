"""
Meta2bAnalyst - Strain-Level Analysis API Routes
Provides direct endpoints for strain composition, alpha, beta, differential, dominance, and replacement analysis.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import AnalysisJob, DataFile, Session as SessionModel
from app.schemas import ErrorResponse, StrainAnalysisRequest, StrainAnalysisResponse
from app.services.strain_analyzer import (
    StrainAnalyzer,
    run_strain_profile,
    run_strain_comparison,
    run_ani_matrix,
    run_strain_pcoa,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────── Data retrieval helpers


def get_strain_dataframe(session_id: str, db: DBSession) -> pd.DataFrame:
    """Get strain-level data for a session."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type.in_(['strain', 'tag2bmap']))
        .first()
    )
    if not data_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No strain data found for this session',
        )

    try:
        df = pd.read_csv(data_file.file_path, sep='\t')
        # Standardize column names
        df.columns = [c.lower().strip() for c in df.columns]
        # Ensure numeric abundance
        if 'abundance' in df.columns:
            df['abundance'] = pd.to_numeric(df['abundance'], errors='coerce')
        return df
    except Exception as e:
        logger.error(f'Failed to parse strain data: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to parse strain data: {str(e)}',
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


def _save_strain_result(session_id: str, job: AnalysisJob, result_data: Dict[str, Any]) -> None:
    """Save strain analysis result to disk and update job record."""
    session_dir = Path('./uploads') / session_id / 'results'
    session_dir.mkdir(parents=True, exist_ok=True)
    result_path = session_dir / f'strain_analysis_{job.id}.json'
    import json
    with open(result_path, 'w') as f:
        json.dump(result_data, f, indent=2, default=str)
    job.result_path = str(result_path)
    job.result_data = result_data


# ─────────────────────────────── Strain Composition


@router.post(
    '/sessions/{session_id}/analyze/strain/composition',
    response_model=StrainAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_strain_composition(
    session_id: str,
    request: StrainAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Generate strain composition stacked bar chart for a target species."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_strain_dataframe(session_id, db)

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='strain_composition',
            parameters={
                'species': request.species,
                'min_ani': request.min_ani,
                'min_coverage': request.min_coverage,
            },
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        analyzer = StrainAnalyzer()
        plot_data = analyzer.plotly_strain_composition(df, request.species)
        result_data = {'plot_data': plot_data}

        _save_strain_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return StrainAnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            species=request.species,
            analysis_type='strain_composition',
            status=job.status,
            result_data=result_data,
            strain_count=None,
            message='Strain composition plot generated',
        )
    except Exception as e:
        db.rollback()
        logger.error(f'Strain composition analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Strain Alpha Diversity


@router.post(
    '/sessions/{session_id}/analyze/strain/alpha',
    response_model=StrainAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_strain_alpha(
    session_id: str,
    request: StrainAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Calculate strain-level alpha diversity for a target species."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_strain_dataframe(session_id, db)

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='strain_alpha',
            parameters={
                'species': request.species,
                'metric': request.parameters.get('metric', 'shannon') if request.parameters else 'shannon',
                'min_ani': request.min_ani,
                'min_coverage': request.min_coverage,
            },
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        analyzer = StrainAnalyzer()
        metric = job.parameters.get('metric', 'shannon')
        alpha_df = analyzer.strain_alpha_diversity(df, metric=metric, species=request.species)

        result_data = {
            'alpha_diversity': alpha_df.to_dict(orient='records'),
            'metric': metric,
        }

        _save_strain_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return StrainAnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            species=request.species,
            analysis_type='strain_alpha',
            status=job.status,
            result_data=result_data,
            strain_count=int(alpha_df['sample_id'].nunique()) if 'sample_id' in alpha_df.columns else None,
            message='Strain alpha diversity calculated',
        )
    except Exception as e:
        db.rollback()
        logger.error(f'Strain alpha diversity analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Strain Beta Diversity


@router.post(
    '/sessions/{session_id}/analyze/strain/beta',
    response_model=StrainAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_strain_beta(
    session_id: str,
    request: StrainAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Calculate strain-level beta diversity distance matrix for a target species."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_strain_dataframe(session_id, db)

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='strain_beta',
            parameters={
                'species': request.species,
                'distance': request.parameters.get('distance', 'braycurtis') if request.parameters else 'braycurtis',
                'min_ani': request.min_ani,
                'min_coverage': request.min_coverage,
            },
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        analyzer = StrainAnalyzer()
        distance = job.parameters.get('distance', 'braycurtis')
        dist_matrix = analyzer.strain_beta_diversity(df, distance=distance, species=request.species)

        result_data = {
            'distance_matrix': dist_matrix.to_dict() if not dist_matrix.empty else {},
            'distance_metric': distance,
        }

        _save_strain_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return StrainAnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            species=request.species,
            analysis_type='strain_beta',
            status=job.status,
            result_data=result_data,
            strain_count=len(dist_matrix.columns) if not dist_matrix.empty else None,
            message='Strain beta diversity calculated',
        )
    except Exception as e:
        db.rollback()
        logger.error(f'Strain beta diversity analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Strain Differential


@router.post(
    '/sessions/{session_id}/analyze/strain/differential',
    response_model=StrainAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_strain_differential(
    session_id: str,
    request: StrainAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Run strain-level differential abundance analysis between two metadata groups."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_strain_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    if metadata_df is None:
        raise HTTPException(status_code=400, detail='Metadata is required for differential analysis')

    group_var = request.parameters.get('group_var') if request.parameters else None
    if group_var is None or group_var not in metadata_df.columns:
        raise HTTPException(status_code=400, detail=f'Valid group_var parameter required in metadata')

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='strain_differential',
            parameters={
                'species': request.species,
                'group_var': group_var,
                'within_species': request.parameters.get('within_species', True) if request.parameters else True,
                'min_ani': request.min_ani,
                'min_coverage': request.min_coverage,
            },
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        analyzer = StrainAnalyzer()
        diff_df = analyzer.strain_differential(
            df, metadata_df, group_var=group_var, species=request.species,
            within_species=job.parameters.get('within_species', True),
        )

        result_data = {
            'differential_results': diff_df.to_dict(orient='records') if not diff_df.empty else [],
            'total_strains_tested': len(diff_df),
            'significant_strains': int((diff_df['pvalue'] < 0.05).sum()) if not diff_df.empty else 0,
        }

        _save_strain_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return StrainAnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            species=request.species,
            analysis_type='strain_differential',
            status=job.status,
            result_data=result_data,
            strain_count=len(diff_df) if not diff_df.empty else None,
            message='Strain differential analysis completed',
        )
    except Exception as e:
        db.rollback()
        logger.error(f'Strain differential analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Strain Dominance Index


@router.post(
    '/sessions/{session_id}/analyze/strain/dominance',
    response_model=StrainAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_strain_dominance(
    session_id: str,
    request: StrainAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Calculate strain dominance index per species."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_strain_dataframe(session_id, db)

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='strain_dominance',
            parameters={
                'species': request.species,
                'min_ani': request.min_ani,
                'min_coverage': request.min_coverage,
            },
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        analyzer = StrainAnalyzer()
        dominance_df = analyzer.strain_dominance_index(df)

        # Filter by species if requested
        if request.species and 'species' in dominance_df.columns:
            dominance_df = dominance_df[dominance_df['species'] == request.species].copy()

        result_data = {
            'dominance_index': dominance_df.to_dict(orient='records') if not dominance_df.empty else [],
        }

        _save_strain_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return StrainAnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            species=request.species,
            analysis_type='strain_dominance',
            status=job.status,
            result_data=result_data,
            strain_count=None,
            message='Strain dominance index calculated',
        )
    except Exception as e:
        db.rollback()
        logger.error(f'Strain dominance analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Strain Replacement Score


@router.post(
    '/sessions/{session_id}/analyze/strain/replacement',
    response_model=StrainAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def analyze_strain_replacement(
    session_id: str,
    request: StrainAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Calculate strain replacement score between two metadata groups."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    df = get_strain_dataframe(session_id, db)
    metadata_df = get_metadata_df(session_id, db)

    if metadata_df is None:
        raise HTTPException(status_code=400, detail='Metadata is required for replacement analysis')

    group_var = request.parameters.get('group_var') if request.parameters else None
    group1 = request.parameters.get('group1') if request.parameters else None
    group2 = request.parameters.get('group2') if request.parameters else None

    if group_var is None or group_var not in metadata_df.columns:
        raise HTTPException(status_code=400, detail='Valid group_var parameter required in metadata')
    if group1 is None or group2 is None:
        raise HTTPException(status_code=400, detail='group1 and group2 parameters are required')

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type='strain_replacement',
            parameters={
                'species': request.species,
                'group_var': group_var,
                'group1': group1,
                'group2': group2,
                'min_ani': request.min_ani,
                'min_coverage': request.min_coverage,
            },
            status='running',
            started_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        analyzer = StrainAnalyzer()
        replacement_score = analyzer.strain_replacement_score(
            df, metadata_df, group_var=group_var, group1=group1, group2=group2,
        )

        # Also get strain composition for each group
        g1_samples = metadata_df[metadata_df[group_var] == group1].index.intersection(df['sample_id'].unique())
        g2_samples = metadata_df[metadata_df[group_var] == group2].index.intersection(df['sample_id'].unique())
        g1_strains = set(df[df['sample_id'].isin(g1_samples)]['strain'].unique())
        g2_strains = set(df[df['sample_id'].isin(g2_samples)]['strain'].unique())

        result_data = {
            'replacement_score': float(replacement_score),
            'group1': str(group1),
            'group2': str(group2),
            'group1_strains': list(g1_strains),
            'group2_strains': list(g2_strains),
            'shared_strains': list(g1_strains & g2_strains),
            'unique_to_group1': list(g1_strains - g2_strains),
            'unique_to_group2': list(g2_strains - g1_strains),
        }

        _save_strain_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return StrainAnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            species=request.species,
            analysis_type='strain_replacement',
            status=job.status,
            result_data=result_data,
            strain_count=None,
            message='Strain replacement score calculated',
        )
    except Exception as e:
        db.rollback()
        logger.error(f'Strain replacement analysis failed: {e}')
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


# ─────────────────────────────── Legacy strain analysis endpoints


@router.post(
    '/sessions/{session_id}/strain-analysis',
    response_model=StrainAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def create_strain_analysis(
    session_id: str,
    request: StrainAnalysisRequest,
    db: DBSession = Depends(get_db),
):
    """Submit a strain-level analysis job (legacy queue-based)."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f'Session {session_id} not found')

    try:
        job = AnalysisJob(
            session_id=session_id,
            job_type=f'strain_{request.analysis_type}',
            parameters={
                'species': request.species,
                'analysis_type': request.analysis_type,
                **(request.parameters or {}),
                'min_ani': request.min_ani,
                'min_coverage': request.min_coverage,
            },
            status='pending',
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        return StrainAnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            species=request.species,
            analysis_type=request.analysis_type,
            status=job.status,
            message='Strain analysis job created',
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f'Failed to create strain analysis job: {str(e)}')


@router.post(
    '/sessions/{session_id}/strain-analysis/{job_id}/run',
    response_model=StrainAnalysisResponse,
    responses={404: {'model': ErrorResponse}, 400: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},
)
async def run_strain_analysis(
    session_id: str,
    job_id: int,
    db: DBSession = Depends(get_db),
):
    """Run a pending strain analysis job (legacy execution path)."""
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).filter(AnalysisJob.session_id == session_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f'Strain analysis job {job_id} not found')

    if job.status not in ('pending', 'failed'):
        raise HTTPException(status_code=400, detail=f'Job is already {job.status}')

    try:
        df = get_strain_dataframe(session_id, db)
        params = job.parameters or {}
        species = params.get('species', '')
        analysis_type = params.get('analysis_type', 'strain_profile')

        job.status = 'running'
        db.commit()

        result_data = None
        strain_count = None

        if analysis_type == 'strain_profile':
            result_data, strain_count = run_strain_profile(df, species, params)
        elif analysis_type == 'strain_comparison':
            result_data = run_strain_comparison(df, species, params)
        elif analysis_type == 'ani_matrix':
            result_data = run_ani_matrix(df, species, params)
        elif analysis_type == 'strain_pcoa':
            result_data = run_strain_pcoa(df, species, params)
        else:
            raise ValueError(f'Unknown strain analysis type: {analysis_type}')

        _save_strain_result(session_id, job, result_data)
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        db.commit()

        return StrainAnalysisResponse(
            job_id=job.id,
            session_id=session_id,
            species=species,
            analysis_type=analysis_type,
            status=job.status,
            result_data=result_data,
            strain_count=strain_count,
            message='Strain analysis completed',
        )
    except Exception as e:
        job.status = 'failed'
        job.error_message = str(e)
        db.commit()
        logger.error(f'Strain analysis job {job_id} failed: {e}')
        raise HTTPException(status_code=500, detail=f'Strain analysis failed: {str(e)}')
