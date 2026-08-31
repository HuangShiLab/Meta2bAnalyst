"""
Meta2bAnalyst - Data Operations API Routes (Inspect, Filter, Normalize)
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.config import settings
from app.models import DataFile, Session as SessionModel
from app.schemas import (
    DataInspectionResponse,
    ErrorResponse,
    FilterRequest,
    FilterResponse,
    NormalizeRequest,
    NormalizeResponse,
)
from app.services.data_parser import parse_data_file
from app.services.data_processor import filter_data, normalize_data
from app.services.data_validator import validate_data_for_analysis as validate_data_integrity

logger = logging.getLogger(__name__)
router = APIRouter()


def get_feature_table_path(session_id: str, db: DBSession) -> Optional[Path]:
    """Get the feature table file path for a session (latest processed version first)."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(
            (DataFile.file_type.in_(["feature_table", "biom", "shared", "microbiome", "filtered_feature_table"]))
            | (DataFile.file_type.like("normalized\\_%", escape="\\"))
        )
        .order_by(DataFile.id.desc())
        .first()
    )
    if data_file:
        return Path(data_file.file_path)
    return None


def get_metadata_path(session_id: str, db: DBSession) -> Optional[Path]:
    """Get the metadata file path for a session."""
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type == "metadata")
        .first()
    )
    if data_file:
        return Path(data_file.file_path)
    return None


def get_dataframe(session_id: str, db: DBSession) -> pd.DataFrame:
    """Get the feature table as a DataFrame for a session."""
    file_path = get_feature_table_path(session_id, db)
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feature table found for this session. Please upload data first.",
        )
    
    try:
        df, _ = parse_data_file(file_path)
        return df
    except Exception as e:
        logger.error(f"Failed to parse data file for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse data file: {str(e)}",
        )


@router.get(
    "/sessions/{session_id}/inspect",
    response_model=DataInspectionResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def inspect_data(
    session_id: str,
    db: DBSession = Depends(get_db),
):
    """Inspect uploaded data and return summary statistics."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    df = get_dataframe(session_id, db)
    
    # Get data file record
    data_file = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type.in_(["feature_table", "biom", "shared"]))
        .first()
    )
    
    # Generate summary statistics
    summary: Dict[str, Any] = {
        "total_reads": int(df.sum().sum()),
        "mean_reads_per_sample": float(df.sum(axis=0).mean()),
        "median_reads_per_sample": float(df.sum(axis=0).median()),
        "std_reads_per_sample": float(df.sum(axis=0).std()),
        "min_reads_per_sample": int(df.sum(axis=0).min()),
        "max_reads_per_sample": int(df.sum(axis=0).max()),
        "sparsity": float((df == 0).sum().sum() / (df.shape[0] * df.shape[1])),
    }
    
    # Add top features by mean abundance
    top_features = df.mean(axis=1).sort_values(ascending=False).head(10)
    summary["top_features"] = {
        str(k): float(v) for k, v in top_features.items()
    }
    
    # Preview first few rows (transposed for display: samples as rows)
    preview_df = df.iloc[:5, :5].T.reset_index()
    preview = preview_df.to_dict(orient="records")

    # Per-sample library sizes for the inspection bar chart
    library_sizes = {str(s): float(v) for s, v in df.sum(axis=0).items()}

    # Metadata cross-check: how many feature-table samples appear in metadata
    metadata_info: Optional[Dict[str, Any]] = None
    metadata_path = get_metadata_path(session_id, db)
    if metadata_path and metadata_path.exists():
        try:
            # Metadata files are samples x variables with a '#SampleID' index
            # column; read directly so the '#' header is not dropped.
            try:
                mdf = pd.read_csv(metadata_path, sep="\t", index_col=0)
            except Exception:
                mdf = pd.read_csv(metadata_path, index_col=0)
            meta_samples = [str(s) for s in mdf.index]
            table_samples = [str(s) for s in df.columns]
            matched = sorted(set(table_samples) & set(meta_samples))
            metadata_info = {
                "metadata_samples": len(meta_samples),
                "table_samples": len(table_samples),
                "matched_samples": len(matched),
                "match_ratio": round(len(matched) / max(len(table_samples), 1), 4),
                "n_metadata_columns": int(mdf.shape[1]),
                "unmatched_table_samples": sorted(set(table_samples) - set(meta_samples))[:20],
                "unmatched_metadata_samples": sorted(set(meta_samples) - set(table_samples))[:20],
            }
        except Exception as e:
            logger.warning(f"Failed to parse metadata for inspection: {e}")
            metadata_info = {"error": str(e)}

    return DataInspectionResponse(
        session_id=session_id,
        file_id=data_file.id if data_file else 0,
        file_type=data_file.file_type if data_file else "unknown",
        row_count=len(df),
        column_count=len(df.columns),
        sample_count=len(df.columns),
        feature_count=len(df.index),
        sample_names=list(df.columns),
        feature_names=list(df.index),
        summary=summary,
        preview=preview,
        library_sizes=library_sizes,
        metadata=metadata_info,
    )


@router.post(
    "/sessions/{session_id}/filter",
    response_model=FilterResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def filter_data_endpoint(
    session_id: str,
    request: FilterRequest,
    db: DBSession = Depends(get_db),
):
    """Filter data based on specified criteria."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    df = get_dataframe(session_id, db)
    row_count_before = len(df)
    column_count_before = len(df.columns)
    
    try:
        filtered_df = filter_data(
            df,
            min_samples=request.min_samples,
            min_abundance=request.min_abundance,
            max_features=request.max_features,
            sample_filter=request.sample_filter,
            feature_filter=request.feature_filter,
            variance_remove_ratio=request.variance_remove_ratio or 0.0,
            variance_based=request.variance_based or "iqr",
            abundance_method=request.abundance_method or "prevalence",
        )
        
        # Save filtered data
        session_dir = Path(settings.UPLOAD_DIR) / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        filtered_path = session_dir / "filtered_feature_table.tsv"
        filtered_df.to_csv(filtered_path, sep="\t")
        
        # Create data file record for filtered data
        filtered_file = DataFile(
            session_id=session_id,
            file_type="filtered_feature_table",
            file_path=str(filtered_path),
            original_name="filtered_feature_table.tsv",
            row_count=len(filtered_df),
            column_count=len(filtered_df.columns),
            sample_count=len(filtered_df.columns),
            feature_count=len(filtered_df.index),
            sample_names=list(filtered_df.columns),
            feature_names=list(filtered_df.index),
        )
        db.add(filtered_file)
        db.commit()
        
        return FilterResponse(
            session_id=session_id,
            row_count_before=row_count_before,
            row_count_after=len(filtered_df),
            column_count_before=column_count_before,
            column_count_after=len(filtered_df.columns),
            samples_removed=column_count_before - len(filtered_df.columns),
            features_removed=row_count_before - len(filtered_df.index),
            status="success",
        )
    
    except Exception as e:
        logger.error(f"Failed to filter data for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to filter data: {str(e)}",
        )


@router.post(
    "/sessions/{session_id}/normalize",
    response_model=NormalizeResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def normalize_data_endpoint(
    session_id: str,
    request: NormalizeRequest,
    db: DBSession = Depends(get_db),
):
    """Normalize data using specified method."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    df = get_dataframe(session_id, db)
    
    try:
        normalized_df = normalize_data(
            df,
            method=request.method,
            target_depth=request.target_depth,
            log_transform=request.log_transform,
        )
        
        # Save normalized data
        session_dir = Path(settings.UPLOAD_DIR) / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = session_dir / f"normalized_{request.method}.tsv"
        normalized_df.to_csv(normalized_path, sep="\t")
        
        # Create data file record
        normalized_file = DataFile(
            session_id=session_id,
            file_type=f"normalized_{request.method}",
            file_path=str(normalized_path),
            original_name=f"normalized_{request.method}.tsv",
            row_count=len(normalized_df),
            column_count=len(normalized_df.columns),
            sample_count=len(normalized_df.columns),
            feature_count=len(normalized_df.index),
            sample_names=list(normalized_df.columns),
            feature_names=list(normalized_df.index),
        )
        db.add(normalized_file)
        db.commit()
        
        return NormalizeResponse(
            session_id=session_id,
            method=request.method,
            row_count=len(normalized_df),
            column_count=len(normalized_df.columns),
            status="success",
            message=f"Data normalized using {request.method} method",
        )
    
    except Exception as e:
        logger.error(f"Failed to normalize data for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to normalize data: {str(e)}",
        )


@router.get(
    "/sessions/{session_id}/metadata/columns",
    responses={404: {"model": ErrorResponse}},
)
async def get_metadata_columns(
    session_id: str,
    max_levels: int = 50,
    db: DBSession = Depends(get_db),
):
    """List the session's metadata columns and their distinct values.

    The UI needs this to populate grouping/comparison selectors. Those lists
    used to be hardcoded in the frontend (["Visit", "Treatment", "Group", ...]),
    so users could not select their own metadata columns at all.

    Args:
        session_id: Session identifier.
        max_levels: Values are only enumerated for columns with at most this
            many distinct levels; anything wider is reported as continuous.

    Returns:
        ``{"columns": [{name, dtype, is_categorical, n_levels, values, n_missing}]}``
    """
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    record = (
        db.query(DataFile)
        .filter(DataFile.session_id == session_id)
        .filter(DataFile.file_type == "metadata")
        .order_by(DataFile.id.desc())
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=404,
            detail="No metadata file has been uploaded for this session.",
        )

    try:
        # Read directly like analysis routes do: the leading '#SampleID' header
        # must not be treated as a comment line (parse_data_file would skip it
        # and misalign every column).
        try:
            meta_df = pd.read_csv(record.file_path, sep="\t", index_col=0)
        except Exception:
            meta_df = pd.read_csv(record.file_path, index_col=0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse metadata: {e}")

    columns = []
    for name in meta_df.columns:
        series = meta_df[name]
        distinct = series.dropna().unique()
        is_categorical = len(distinct) <= max_levels
        columns.append({
            "name": str(name),
            "dtype": str(series.dtype),
            "is_categorical": bool(is_categorical),
            "n_levels": int(len(distinct)),
            # Sorted so the UI order is stable and independent of file row order.
            "values": sorted(str(v) for v in distinct) if is_categorical else [],
            "n_missing": int(series.isna().sum()),
        })

    return {
        "session_id": session_id,
        "n_samples": int(len(meta_df)),
        "sample_ids": [str(s) for s in meta_df.index],
        "columns": columns,
    }
