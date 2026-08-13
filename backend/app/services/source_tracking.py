"""
Meta2bAnalyst - Source Tracking Module (FEAST-style)
Estimates the proportion of microbial sources contributing to a sink (mixed) sample.

References:
  - FEAST: Shenhav et al. 2019, Nat Methods 16:627-632
  - SourceTracker: Knights et al. 2011, Nat Methods 8:761-763
"""
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.optimize import nnls
from scipy.spatial.distance import braycurtis

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=RuntimeWarning)


def _sanitize_json(obj: Any) -> Any:
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, (np.bool_, np.bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return _sanitize_json(obj.to_dict(orient='records'))
    if isinstance(obj, pd.Series):
        return _sanitize_json(obj.to_dict())
    return obj


# ─────────────────────────────── Source Tracking Core

def estimate_source_proportions(
    sink: pd.Series,
    sources: pd.DataFrame,
    method: str = "nnls",
) -> Dict[str, Any]:
    """Estimate source proportions for a single sink sample.
    
    Args:
        sink: Sink sample vector (feature abundances).
        sources: Source matrix (features x source_samples).
        method: 'nnls' (non-negative least squares) or 'em' (expectation-maximization).
        
    Returns:
        Dict with source proportions and fit quality.
    """
    # Get common features
    common_features = sink.index.intersection(sources.index)
    if len(common_features) < 3:
        return {"error": f"Insufficient common features: {len(common_features)}"}
    
    sink_vec = sink[common_features].values
    source_matrix = sources.loc[common_features].values
    
    # Normalize to proportions
    sink_vec = sink_vec / sink_vec.sum() if sink_vec.sum() > 0 else sink_vec
    source_matrix = source_matrix / source_matrix.sum(axis=0, keepdims=True)
    source_matrix = np.nan_to_num(source_matrix, nan=0.0)
    
    if method == "nnls":
        # Non-negative least squares
        proportions, residual = nnls(source_matrix, sink_vec)
        
        # Normalize proportions to sum to 1
        if proportions.sum() > 0:
            proportions = proportions / proportions.sum()
        
        # Compute fit quality (1 - Bray-Curtis distance)
        predicted = source_matrix @ proportions
        fit_quality = 1 - braycurtis(sink_vec, predicted)
        
    else:
        # Simple EM-like approach
        proportions = np.ones(source_matrix.shape[1]) / source_matrix.shape[1]
        
        for _ in range(100):
            # E-step: compute expected contributions
            predicted = source_matrix @ proportions
            
            # M-step: update proportions
            new_proportions = np.zeros_like(proportions)
            for j in range(len(proportions)):
                contrib = source_matrix[:, j] * proportions[j]
                new_proportions[j] = np.sum(contrib * sink_vec / (predicted + 1e-10))
            
            new_proportions = new_proportions / new_proportions.sum()
            
            if np.max(np.abs(new_proportions - proportions)) < 1e-6:
                break
            
            proportions = new_proportions
        
        predicted = source_matrix @ proportions
        fit_quality = 1 - braycurtis(sink_vec, predicted)
    
    source_names = list(sources.columns)
    
    return {
        "proportions": dict(zip(source_names, proportions.tolist())),
        "fit_quality": fit_quality,
        "residual": float(residual) if method == "nnls" else None,
        "method": method,
        "n_features": len(common_features),
    }


def run_source_tracking(
    sink_df: pd.DataFrame,
    source_df: pd.DataFrame,
    method: str = "nnls",
) -> pd.DataFrame:
    """Run source tracking on multiple sink samples.
    
    Args:
        sink_df: Sink samples (features x sink_samples).
        source_df: Source samples (features x source_samples).
        method: 'nnls' or 'em'.
        
    Returns:
        DataFrame with source proportions for each sink sample.
    """
    results = []
    
    for sink_sample in sink_df.columns:
        sink = sink_df[sink_sample]
        result = estimate_source_proportions(sink, source_df, method=method)
        
        if "error" in result:
            logger.warning(f"Source tracking failed for {sink_sample}: {result['error']}")
            continue
        
        row = {"sink_sample": sink_sample, "fit_quality": result["fit_quality"]}
        row.update(result["proportions"])
        results.append(row)
    
    if not results:
        return pd.DataFrame()
    
    return pd.DataFrame(results)


# ─────────────────────────────── Plotly Visualizations

def plotly_source_proportions(proportions_df: pd.DataFrame) -> dict:
    """Generate stacked bar plot of source proportions.
    
    Args:
        proportions_df: Result from run_source_tracking().
        
    Returns:
        Plotly figure JSON dict.
    """
    if proportions_df.empty:
        return go.Figure().update_layout(title="No source tracking data").to_dict()
    
    # Melt DataFrame for plotting
    id_vars = ["sink_sample", "fit_quality"]
    source_cols = [c for c in proportions_df.columns if c not in id_vars]
    
    df_melt = proportions_df.melt(
        id_vars=["sink_sample"],
        value_vars=source_cols,
        var_name="Source",
        value_name="Proportion",
    )
    
    fig = px.bar(
        df_melt,
        x="sink_sample",
        y="Proportion",
        color="Source",
        title="Source Tracking: Estimated Proportions",
        labels={"sink_sample": "Sink Sample", "Proportion": "Proportion"},
    )
    
    fig.update_layout(
        template="plotly_white",
        height=400,
        width=max(600, len(proportions_df) * 40),
        barmode="stack",
        xaxis_tickangle=-45,
    )
    
    return fig.to_dict()


def plotly_source_heatmap(proportions_df: pd.DataFrame) -> dict:
    """Generate heatmap of source proportions.
    
    Args:
        proportions_df: Result from run_source_tracking().
        
    Returns:
        Plotly figure JSON dict.
    """
    if proportions_df.empty:
        return go.Figure().update_layout(title="No source tracking data").to_dict()
    
    source_cols = [c for c in proportions_df.columns if c not in ["sink_sample", "fit_quality"]]
    
    if not source_cols:
        return go.Figure().update_layout(title="No source columns").to_dict()
    
    fig = px.imshow(
        proportions_df[source_cols].values,
        x=source_cols,
        y=proportions_df["sink_sample"].values,
        color_continuous_scale="Blues",
        aspect="auto",
        title="Source Proportions Heatmap",
    )
    
    fig.update_layout(
        xaxis_title="Source",
        yaxis_title="Sink Sample",
        template="plotly_white",
        height=max(400, len(proportions_df) * 20),
        width=max(500, len(source_cols) * 80),
    )
    
    return fig.to_dict()


def plotly_source_pie(proportions_df: pd.DataFrame, sink_sample: str) -> dict:
    """Generate pie chart for a single sink sample.
    
    Args:
        proportions_df: Result from run_source_tracking().
        sink_sample: Sample name to plot.
        
    Returns:
        Plotly figure JSON dict.
    """
    row = proportions_df[proportions_df["sink_sample"] == sink_sample]
    
    if row.empty:
        return go.Figure().update_layout(title=f"Sample {sink_sample} not found").to_dict()
    
    source_cols = [c for c in proportions_df.columns if c not in ["sink_sample", "fit_quality"]]
    values = row[source_cols].values[0]
    
    fig = go.Figure(data=[go.Pie(
        labels=source_cols,
        values=values,
        hole=0.4,
        textinfo="label+percent",
        textfont_size=10,
    )])
    
    fig.update_layout(
        title=f"Source Proportions: {sink_sample}",
        template="plotly_white",
        height=400,
        width=400,
    )
    
    return fig.to_dict()


# ─────────────────────────────── Main Runner

def run_source_tracking_analysis(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run complete source tracking analysis.
    
    Args:
        df: Feature table (features x samples).
        metadata_df: Optional metadata with source/sink designations.
        parameters: Dict with keys:
            - sink_samples: List of sink sample names (if metadata not provided).
            - source_samples: List of source sample names (if metadata not provided).
            - source_column: Metadata column indicating source/sink (default 'source_type').
            - method: 'nnls' or 'em' (default 'nnls').
            
    Returns:
        Dict with source proportions, plots, and summary statistics.
    """
    params = parameters or {}
    sink_samples = params.get("sink_samples", [])
    source_samples = params.get("source_samples", [])
    source_column = params.get("source_column", "source_type")
    method = params.get("method", "nnls")
    
    logger.info(f"Starting source tracking: method={method}")
    
    # Determine sinks and sources from metadata if provided
    if metadata_df is not None and source_column in metadata_df.columns:
        sink_mask = metadata_df[source_column] == "sink"
        source_mask = metadata_df[source_column] == "source"
        
        sink_samples = metadata_df[sink_mask].index.intersection(df.columns).tolist()
        source_samples = metadata_df[source_mask].index.intersection(df.columns).tolist()
    
    # If still not determined, use first sample as sink, rest as sources
    if not sink_samples and not source_samples:
        if len(df.columns) >= 2:
            sink_samples = [df.columns[0]]
            source_samples = df.columns[1:].tolist()
        else:
            return {"error": "Need at least 2 samples for source tracking"}
    
    if not sink_samples:
        return {"error": "No sink samples specified"}
    
    if not source_samples:
        return {"error": "No source samples specified"}
    
    # Subset data
    sink_df = df[sink_samples]
    source_df = df[source_samples]
    
    # Run source tracking
    proportions_df = run_source_tracking(sink_df, source_df, method=method)
    
    if proportions_df.empty:
        return {"error": "Source tracking failed for all samples"}
    
    # Summary statistics
    source_cols = [c for c in proportions_df.columns if c not in ["sink_sample", "fit_quality"]]
    summary = {
        "n_sink_samples": len(proportions_df),
        "n_source_types": len(source_cols),
        "mean_fit_quality": float(proportions_df["fit_quality"].mean()),
        "source_types": source_cols,
    }
    
    # Mean proportions across all sinks
    mean_props = proportions_df[source_cols].mean().to_dict()
    summary["mean_proportions"] = mean_props
    
    # Dominant source for each sink
    dominant_sources = []
    for _, row in proportions_df.iterrows():
        max_source = row[source_cols].idxmax()
        max_prop = row[source_cols].max()
        dominant_sources.append({
            "sink_sample": row["sink_sample"],
            "dominant_source": max_source,
            "proportion": max_prop,
        })
    
    # Plots
    plots = {
        "source_proportions": plotly_source_proportions(proportions_df),
        "source_heatmap": plotly_source_heatmap(proportions_df),
    }
    
    # Add pie chart for first sink
    if not proportions_df.empty:
        plots["source_pie"] = plotly_source_pie(proportions_df, proportions_df.iloc[0]["sink_sample"])
    
    # Build result
    result = _sanitize_json({
        "method": method,
        "n_sink_samples": len(sink_samples),
        "n_source_samples": len(source_samples),
        "summary": summary,
        "proportions": proportions_df.to_dict(orient="records"),
        "dominant_sources": dominant_sources,
        "plots": plots,
    })
    
    logger.info("Source tracking complete")
    return result
