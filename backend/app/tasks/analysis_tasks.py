"""
Meta2bAnalyst - Celery Async Analysis Tasks
Implements asynchronous versions of all analysis operations.
"""
import json
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from app.celery_app import celery_app
from app.services.r_analysis import run_deseq2, run_edger
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
from app.services.strain_analyzer import StrainAnalyzer
from app.services.data_parser import parse_data_file
from app.services.orientation import resolve_feature_table, OrientationError

logger = logging.getLogger(__name__)


def _db_session():
    """Open a DB session inside a worker (shares DATABASE_URL with the backend)."""
    from app.database import SessionLocal
    return SessionLocal()

# ─────────────────────────────── Task status helpers


def _update_task_state(self, state: str, meta: Dict[str, Any]) -> None:
    """Update Celery task state with metadata."""
    self.update_state(state=state, meta=meta)


# Feature-table file types in order of preference for the single-omics
# (microbiome) analyses these tasks implement. 'metabolome' is last so a
# multi-omics session never silently runs microbiome stats on the wrong omics.
_FEATURE_TYPE_PREFERENCE = (
    'microbiome', 'metaphlan', 'feature_table', 'filtered_feature_table',
    'normalized_relative', 'biom', 'shared', 'metabolome',
)


def _load_session_data(session_id: str) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Load feature table and metadata for a session.

    DB-driven, mirroring the sync route helpers: the previous disk-glob version
    took the FIRST parseable file as the feature table -- which could be the
    metadata file itself (parsed with a mangled delimiter into a garbage
    260x11 frame) or the metabolome table of a multi-omics session. Orientation
    is resolved against the metadata exactly like the sync path.
    """
    from app.models import DataFile

    db = _db_session()
    try:
        files = (
            db.query(DataFile)
            .filter(DataFile.session_id == session_id)
            .order_by(DataFile.id.desc())
            .all()
        )
    finally:
        db.close()

    metadata_df = _load_metadata(files)

    df = None
    for wanted in _FEATURE_TYPE_PREFERENCE:
        data_file = next((f for f in files if f.file_type == wanted), None)
        if data_file is None:
            continue
        try:
            parsed, _ = parse_data_file(Path(data_file.file_path), file_type=wanted, use_chunks=True)
        except Exception as e:
            logger.error(f'Failed to parse {data_file.file_path}: {e}')
            continue
        try:
            df, report = resolve_feature_table(parsed, metadata_df, name=data_file.original_name or wanted)
        except OrientationError as e:
            # Fail loudly: running ordination/statistics on a mis-oriented
            # table silently computes nonsense.
            raise ValueError(f'Orientation error for {data_file.original_name}: {e}')
        for w in report.warnings:
            logger.warning('Session %s: %s', session_id, w)
        logger.info(f'Loaded feature table ({wanted}): {df.shape}')
        break

    # Legacy fallback for sessions with no DB rows (should not happen, but
    # keeps old uploads usable): glob the upload dir, EXCLUDING metadata files.
    if df is None:
        uploads_dir = Path("./uploads") / session_id
        for file_path in sorted(uploads_dir.glob("*")):
            if not (file_path.is_file() and file_path.suffix in (".csv", ".tsv", ".txt", ".biom", ".shared")):
                continue
            if "metadata" in file_path.name.lower():
                continue
            try:
                parsed, _ = parse_data_file(file_path)
                df, _ = resolve_feature_table(parsed, metadata_df, name=file_path.name)
                logger.info(f'Loaded feature table (disk fallback): {df.shape}')
                break
            except Exception:
                continue

    return df, metadata_df


def _load_metadata(files) -> Optional[pd.DataFrame]:
    """Newest metadata file for the session, tab- then comma-separated."""
    data_file = next((f for f in files if f.file_type == 'metadata'), None)
    if data_file is None:
        return None
    try:
        try:
            return pd.read_csv(data_file.file_path, sep='\t', index_col=0)
        except Exception:
            return pd.read_csv(data_file.file_path, index_col=0)
    except Exception:
        return None


def _save_result(session_id: str, job_id: str, task_name: str, result_data: Dict[str, Any]) -> str:
    """Save task result to session directory and return path."""
    session_dir = Path("./uploads") / session_id / "results"
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Save as JSON
    result_path = session_dir / f"{task_name}_{job_id}.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2, default=str)
    
    # Also save as pickle for large data structures
    pickle_path = session_dir / f"{task_name}_{job_id}.pkl"
    try:
        with open(pickle_path, "wb") as f:
            pickle.dump(result_data, f)
    except Exception as e:
        logger.warning(f"Failed to pickle result: {e}")
    
    logger.info(f"Saved result to {result_path}")
    return str(result_path)


# ─────────────────────────────── Alpha Diversity Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def alpha_diversity_task(
    self,
    session_id: str,
    metrics: list,
    grouping: Optional[str] = None,
) -> Dict[str, Any]:
    """Alpha diversity asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading data..."})
    
    df, metadata_df = _load_session_data(session_id)
    if df is None:
        raise ValueError(f"No feature table found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 30, "message": "Computing alpha diversity..."})
    
    params = {"indices": metrics, "group_column": grouping}
    result_data = run_alpha_diversity(df, metadata_df, params)
    
    # Generate Plotly chart if metadata available
    if metadata_df is not None and grouping and grouping in metadata_df.columns:
        engine = AnalysisEngine()
        alpha_df = engine.alpha_diversity(df, metrics=metrics)
        plot_data = engine.plotly_alpha_boxplot(alpha_df, metadata_df, grouping, metrics[0] if metrics else "shannon")
        result_data["plot_data"] = plot_data
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "alpha_diversity", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "alpha_diversity",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
        "feature_count": len(df.index),
        "sample_count": len(df.columns),
    }


# ─────────────────────────────── Beta Diversity Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def beta_diversity_task(
    self,
    session_id: str,
    distance: str = "braycurtis",
    method: str = "braycurtis",
    grouping: Optional[str] = None,
) -> Dict[str, Any]:
    """Beta diversity asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading data..."})
    
    df, metadata_df = _load_session_data(session_id)
    if df is None:
        raise ValueError(f"No feature table found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 40, "message": "Computing beta diversity..."})
    
    params = {"metric": distance, "group_column": grouping}
    result_data = run_beta_diversity(df, metadata_df, params)
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "beta_diversity", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "beta_diversity",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
        "feature_count": len(df.index),
        "sample_count": len(df.columns),
    }


# ─────────────────────────────── Differential Analysis Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def differential_task(
    self,
    session_id: str,
    method: str = "mannwhitney",
    group_var: str = "",
    group1: str = "",
    group2: str = "",
    p_adjust: str = "BH",
) -> Dict[str, Any]:
    """Differential abundance asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading data..."})
    
    df, metadata_df = _load_session_data(session_id)
    if df is None:
        raise ValueError(f"No feature table found for session {session_id}")
    if metadata_df is None:
        raise ValueError(f"No metadata found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 40, "message": "Running differential analysis..."})
    
    params = {
        "group_column": group_var,
        "test_method": method,
        "pvalue_threshold": 0.05,
    }
    
    groups = metadata_df[group_var].dropna().unique()
    if method in ('deseq2', 'DESeq2') and len(groups) == 2:
        g1, g2 = groups[0], groups[1]
        diff_df = run_deseq2(df, metadata_df, group_var, g1, g2)
        result_data = {
            'group_column': group_var,
            'group1': str(g1),
            'group2': str(g2),
            'test_method': 'DESeq2',
            'significant_features': diff_df[diff_df['padj'] < 0.05].to_dict(orient='records'),
            'all_features': diff_df.to_dict(orient='records'),
        }
    elif method in ('edger', 'edgeR') and len(groups) == 2:
        g1, g2 = groups[0], groups[1]
        diff_df = run_edger(df, metadata_df, group_var, g1, g2)
        result_data = {
            'group_column': group_var,
            'group1': str(g1),
            'group2': str(g2),
            'test_method': 'edgeR',
            'significant_features': diff_df[diff_df['FDR'] < 0.05].to_dict(orient='records'),
            'all_features': diff_df.to_dict(orient='records'),
        }
    else:
        result_data = run_differential_analysis(df, metadata_df, params)
    
    # Generate volcano plot
    if "all_features" in result_data and len(result_data["all_features"]) > 0:
        engine = AnalysisEngine()
        diff_df = pd.DataFrame(result_data["all_features"])
        if "log2_fold_change" in diff_df.columns:
            diff_df = diff_df.rename(columns={"log2_fold_change": "log2FC"})
        if "log2FoldChange" in diff_df.columns:
            diff_df = diff_df.rename(columns={"log2FoldChange": "log2FC"})
        if "padj" in diff_df.columns:
            diff_df = diff_df.rename(columns={"padj": "pvalue"})
        if "FDR" in diff_df.columns:
            diff_df = diff_df.rename(columns={"FDR": "pvalue"})
        if "pvalue" in diff_df.columns and "log2FC" in diff_df.columns:
            plot_data = engine.plotly_volcano(diff_df)
            result_data["plot_data"] = plot_data
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "differential", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "differential",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
        "feature_count": len(df.index),
        "sample_count": len(df.columns),
    }


# ─────────────────────────────── PCoA Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def pcoa_task(
    self,
    session_id: str,
    distance: str = "braycurtis",
    grouping: Optional[str] = None,
) -> Dict[str, Any]:
    """PCoA asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading data..."})
    
    df, metadata_df = _load_session_data(session_id)
    if df is None:
        raise ValueError(f"No feature table found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 40, "message": "Computing PCoA..."})
    
    params = {"metric": distance, "group_column": grouping}
    result_data = run_pcoa(df, metadata_df, params)
    
    # Generate Plotly scatter
    if metadata_df is not None and grouping and grouping in metadata_df.columns:
        engine = AnalysisEngine()
        dist_matrix = engine.beta_diversity(df, distance=distance)
        pcoa_result = engine.pcoa(dist_matrix)
        plot_data = engine.plotly_pcoa_scatter(pcoa_result, metadata_df, grouping)
        result_data["plot_data"] = plot_data
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "pcoa", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "pcoa",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
        "feature_count": len(df.index),
        "sample_count": len(df.columns),
    }


# ─────────────────────────────── Heatmap Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def heatmap_task(
    self,
    session_id: str,
    n_top: int = 50,
) -> Dict[str, Any]:
    """Heatmap generation asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading data..."})
    
    df, metadata_df = _load_session_data(session_id)
    if df is None:
        raise ValueError(f"No feature table found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 40, "message": "Generating heatmap..."})
    
    params = {"top_n": n_top, "cluster_rows": True, "cluster_cols": True, "normalize": "zscore"}
    result_data = run_heatmap(df, metadata_df, params)
    
    # Generate Plotly heatmap
    engine = AnalysisEngine()
    plot_data = engine.plotly_heatmap(df, metadata_df)
    result_data["plot_data"] = plot_data
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "heatmap", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "heatmap",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
        "feature_count": len(df.index),
        "sample_count": len(df.columns),
    }


# ─────────────────────────────── Random Forest Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def random_forest_task(
    self,
    session_id: str,
    group_var: str = "",
    n_estimators: int = 500,
) -> Dict[str, Any]:
    """Random Forest asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading data..."})
    
    df, metadata_df = _load_session_data(session_id)
    if df is None:
        raise ValueError(f"No feature table found for session {session_id}")
    if metadata_df is None:
        raise ValueError(f"No metadata found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 40, "message": "Training Random Forest..."})
    
    params = {"group_column": group_var, "n_estimators": n_estimators}
    result_data = run_random_forest(df, metadata_df, params)
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "random_forest", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "random_forest",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
        "feature_count": len(df.index),
        "sample_count": len(df.columns),
    }


# ─────────────────────────────── Strain Composition Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def strain_composition_task(
    self,
    session_id: str,
    species: str,
) -> Dict[str, Any]:
    """Strain composition asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading strain data..."})
    
    uploads_dir = Path("./uploads") / session_id
    strain_df = None
    for file_path in uploads_dir.glob("*"):
        if file_path.is_file() and "strain" in file_path.name.lower():
            try:
                strain_df = pd.read_csv(file_path, sep="\t")
                strain_df.columns = [c.lower().strip() for c in strain_df.columns]
                if "abundance" in strain_df.columns:
                    strain_df["abundance"] = pd.to_numeric(strain_df["abundance"], errors="coerce")
                break
            except Exception:
                continue
    
    if strain_df is None:
        raise ValueError(f"No strain data found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 40, "message": "Generating strain composition..."})
    
    analyzer = StrainAnalyzer()
    plot_data = analyzer.plotly_strain_composition(strain_df, species)
    result_data = {"plot_data": plot_data}
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "strain_composition", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "strain_composition",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
        "species": species,
    }


# ─────────────────────────────── Strain Differential Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def strain_differential_task(
    self,
    session_id: str,
    group_var: str = "",
    species: str = "",
) -> Dict[str, Any]:
    """Strain-level differential analysis asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading strain data..."})
    
    uploads_dir = Path("./uploads") / session_id
    strain_df = None
    for file_path in uploads_dir.glob("*"):
        if file_path.is_file() and "strain" in file_path.name.lower():
            try:
                strain_df = pd.read_csv(file_path, sep="\t")
                strain_df.columns = [c.lower().strip() for c in strain_df.columns]
                if "abundance" in strain_df.columns:
                    strain_df["abundance"] = pd.to_numeric(strain_df["abundance"], errors="coerce")
                break
            except Exception:
                continue
    
    if strain_df is None:
        raise ValueError(f"No strain data found for session {session_id}")
    
    # Load metadata
    metadata_df = None
    for file_path in uploads_dir.glob("*"):
        if file_path.is_file() and "metadata" in file_path.name.lower():
            try:
                metadata_df = pd.read_csv(file_path, sep="\t", index_col=0)
                break
            except Exception:
                continue
    
    if metadata_df is None:
        raise ValueError(f"No metadata found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 40, "message": "Running strain differential analysis..."})
    
    analyzer = StrainAnalyzer()
    diff_df = analyzer.strain_differential(strain_df, metadata_df, group_var=group_var, species=species or None)
    
    result_data = {
        "differential_results": diff_df.to_dict(orient="records") if not diff_df.empty else [],
        "total_strains_tested": len(diff_df),
        "significant_strains": int((diff_df["pvalue"] < 0.05).sum()) if not diff_df.empty else 0,
    }
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "strain_differential", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "strain_differential",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
        "species": species,
    }


# ─────────────────────────────── NMDS Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def nmds_task(
    self,
    session_id: str,
    distance: str = "braycurtis",
    n_components: int = 2,
) -> Dict[str, Any]:
    """NMDS asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading data..."})
    
    df, metadata_df = _load_session_data(session_id)
    if df is None:
        raise ValueError(f"No feature table found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 40, "message": "Computing NMDS..."})
    
    params = {"metric": distance, "n_components": n_components}
    result_data = run_nmds(df, metadata_df, params)
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "nmds", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "nmds",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
    }


# ─────────────────────────────── PERMANOVA Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def permanova_task(
    self,
    session_id: str,
    distance: str = "braycurtis",
    group_var: str = "",
    n_permutations: int = 999,
) -> Dict[str, Any]:
    """PERMANOVA asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading data..."})
    
    df, metadata_df = _load_session_data(session_id)
    if df is None:
        raise ValueError(f"No feature table found for session {session_id}")
    if metadata_df is None:
        raise ValueError(f"No metadata found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 40, "message": "Running PERMANOVA..."})
    
    params = {"metric": distance, "group_column": group_var, "n_permutations": n_permutations}
    result_data = run_permanova(df, metadata_df, params)
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "permanova", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "permanova",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
    }


# ─────────────────────────────── ANOSIM Task

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def anosim_task(
    self,
    session_id: str,
    distance: str = "braycurtis",
    group_var: str = "",
    n_permutations: int = 999,
) -> Dict[str, Any]:
    """ANOSIM asynchronous task."""
    _update_task_state(self, "STARTED", {"progress": 10, "message": "Loading data..."})
    
    df, metadata_df = _load_session_data(session_id)
    if df is None:
        raise ValueError(f"No feature table found for session {session_id}")
    if metadata_df is None:
        raise ValueError(f"No metadata found for session {session_id}")
    
    _update_task_state(self, "STARTED", {"progress": 40, "message": "Running ANOSIM..."})
    
    params = {"metric": distance, "group_column": group_var, "n_permutations": n_permutations}
    result_data = run_anosim(df, metadata_df, params)
    
    _update_task_state(self, "STARTED", {"progress": 80, "message": "Saving results..."})
    result_path = _save_result(session_id, self.request.id, "anosim", result_data)
    
    return {
        "job_id": self.request.id,
        "session_id": session_id,
        "task": "anosim",
        "status": "SUCCESS",
        "result_path": result_path,
        "result_data": result_data,
    }
