"""
Meta2bAnalyst - Cross-omics Integration Module (Procrustes + Mantel Test)
Implements Procrustes analysis and Mantel test for comparing sample structures
across different omics data types (e.g., 16S vs metabolomics).

References:
  - Procrustes: Gower 1975, Psychometrika 40:33-51
  - Mantel: Mantel 1967, Cancer Res 27:209-220
"""
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.spatial.distance import braycurtis, pdist, squareform
from scipy.stats import pearsonr, spearmanr

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


# ─────────────────────────────── Procrustes Analysis

def procrustes_analysis(
    X: np.ndarray,
    Y: np.ndarray,
    scale: bool = True,
) -> Dict[str, Any]:
    """Perform Procrustes analysis to align two matrices.
    
    Finds optimal rotation, translation, and scaling to minimize sum of squared
    differences between X and Y.
    
    Args:
        X: Reference matrix (n_samples x n_features1).
        Y: Matrix to align (n_samples x n_features2).
        scale: If True, allow scaling.
        
    Returns:
        Dict with transformed Y, m2 (sum of squared errors), and transformation params.
    """
    n, m = X.shape
    ny, my = Y.shape
    
    if n != ny:
        raise ValueError(f"X and Y must have same number of rows, got {n} and {ny}")
    
    # Center both matrices
    X_centered = X - X.mean(axis=0)
    Y_centered = Y - Y.mean(axis=0)
    
    # Compute optimal rotation via SVD
    XY = X_centered.T @ Y_centered
    U, S, Vt = np.linalg.svd(XY)
    R = U @ Vt
    
    # Ensure proper rotation (det(R) = 1)
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Vt
    
    # Compute optimal scaling
    if scale:
        norm_X = np.linalg.norm(X_centered)
        norm_YR = np.linalg.norm(Y_centered @ R.T)
        if norm_YR > 0:
            s = norm_X / norm_YR
        else:
            s = 1.0
    else:
        s = 1.0
    
    # Transform Y
    Y_transformed = s * (Y_centered @ R.T) + X.mean(axis=0)
    
    # Compute m2 (sum of squared errors)
    m2 = np.sum((X - Y_transformed) ** 2)
    
    # Normalized m2 (0 = perfect fit, 1 = no fit)
    norm_X2 = np.sum(X_centered ** 2)
    normalized_m2 = m2 / norm_X2 if norm_X2 > 0 else 1.0
    
    return {
        "Y_transformed": Y_transformed,
        "rotation_matrix": R,
        "scale_factor": s,
        "translation": X.mean(axis=0),
        "m2": m2,
        "normalized_m2": normalized_m2,
        "n_samples": n,
    }


def run_procrustes(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    method: str = "pcoa",
    n_components: int = 2,
) -> Dict[str, Any]:
    """Run Procrustes analysis on two feature tables.
    
    Args:
        df1: First feature table (features x samples).
        df2: Second feature table (features x samples).
        method: 'pcoa' or 'nmds' for dimensionality reduction before Procrustes.
        n_components: Number of dimensions to keep.
        
    Returns:
        Dict with Procrustes results and coordinates for plotting.
    """
    # Get common samples
    common_samples = df1.columns.intersection(df2.columns)
    if len(common_samples) < 3:
        return {"error": f"Need >=3 common samples, got {len(common_samples)}"}
    
    df1_common = df1[common_samples].T  # samples x features
    df2_common = df2[common_samples].T
    
    # Dimensionality reduction
    if method == "pcoa":
        from sklearn.decomposition import PCA
        
        # Standardize
        X_std = (df1_common - df1_common.mean(axis=0)) / (df1_common.std(axis=0) + 1e-10)
        Y_std = (df2_common - df2_common.mean(axis=0)) / (df2_common.std(axis=0) + 1e-10)
        
        # PCA
        pca_X = PCA(n_components=min(n_components, len(common_samples) - 1))
        pca_Y = PCA(n_components=min(n_components, len(common_samples) - 1))
        
        X_coords = pca_X.fit_transform(X_std.fillna(0))
        Y_coords = pca_Y.fit_transform(Y_std.fillna(0))
    else:
        # Direct use (if already same dimensionality)
        X_coords = df1_common.values
        Y_coords = df2_common.values
    
    # Procrustes
    result = procrustes_analysis(X_coords, Y_coords, scale=True)
    
    # Build coordinate DataFrames
    coords_df = pd.DataFrame({
        "sample": common_samples,
        "X_PC1": X_coords[:, 0],
        "X_PC2": X_coords[:, 1] if X_coords.shape[1] > 1 else np.zeros(len(common_samples)),
        "Y_PC1": result["Y_transformed"][:, 0],
        "Y_PC2": result["Y_transformed"][:, 1] if result["Y_transformed"].shape[1] > 1 else np.zeros(len(common_samples)),
    })
    
    return {
        "method": method,
        "n_common_samples": len(common_samples),
        "common_samples": list(common_samples),
        "m2": result["m2"],
        "normalized_m2": result["normalized_m2"],
        "scale_factor": result["scale_factor"],
        "coordinates": coords_df.to_dict(orient="records"),
    }


# ─────────────────────────────── Mantel Test

def mantel_test(
    dist1: np.ndarray,
    dist2: np.ndarray,
    method: str = "pearson",
    n_permutations: int = 999,
) -> Dict[str, Any]:
    """Perform Mantel test to compare two distance matrices.
    
    Args:
        dist1, dist2: Distance matrices (flattened upper triangles).
        method: 'pearson' or 'spearman'.
        n_permutations: Number of permutations for p-value.
        
    Returns:
        Dict with correlation coefficient and p-value.
    """
    if len(dist1) != len(dist2):
        raise ValueError("Distance matrices must have same number of elements")
    
    # Remove diagonal and lower triangle (if squareform)
    if method == "spearman":
        corr, _ = spearmanr(dist1, dist2)
    else:
        corr, _ = pearsonr(dist1, dist2)
    
    # Permutation test
    rng = np.random.RandomState(seed=42)
    perm_corrs = []
    for _ in range(n_permutations):
        perm = rng.permutation(len(dist2))
        perm_dist2 = dist2[perm]
        if method == "spearman":
            pc, _ = spearmanr(dist1, perm_dist2)
        else:
            pc, _ = pearsonr(dist1, perm_dist2)
        perm_corrs.append(pc)
    
    perm_corrs = np.array(perm_corrs)
    p_value = (np.sum(np.abs(perm_corrs) >= np.abs(corr)) + 1) / (n_permutations + 1)
    
    return {
        "correlation": float(corr),
        "p_value": float(p_value),
        "n_permutations": n_permutations,
        "method": method,
    }


def run_mantel(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    metric: str = "braycurtis",
    method: str = "pearson",
    n_permutations: int = 999,
) -> Dict[str, Any]:
    """Run Mantel test on two feature tables.
    
    Args:
        df1, df2: Feature tables (features x samples).
        metric: Distance metric for both tables.
        method: 'pearson' or 'spearman'.
        n_permutations: Number of permutations.
        
    Returns:
        Dict with Mantel test results.
    """
    common_samples = df1.columns.intersection(df2.columns)
    if len(common_samples) < 3:
        return {"error": f"Need >=3 common samples, got {len(common_samples)}"}
    
    # Compute distance matrices
    dist1_matrix = squareform(pdist(df1[common_samples].T, metric=metric))
    dist2_matrix = squareform(pdist(df2[common_samples].T, metric=metric))
    
    # Extract upper triangle (no diagonal)
    n = len(common_samples)
    idx = np.triu_indices(n, k=1)
    dist1_flat = dist1_matrix[idx]
    dist2_flat = dist2_matrix[idx]
    
    # Mantel test
    result = mantel_test(dist1_flat, dist2_flat, method=method, n_permutations=n_permutations)
    
    return {
        "n_common_samples": len(common_samples),
        "common_samples": list(common_samples),
        **result,
    }


# ─────────────────────────────── Plotly Visualizations

def plotly_procrustes(coords_df: pd.DataFrame, metadata_df: Optional[pd.DataFrame] = None,
                      group_column: Optional[str] = None) -> dict:
    """Generate Procrustes comparison plot.
    
    Args:
        coords_df: DataFrame with X_PC1, X_PC2, Y_PC1, Y_PC2 columns.
        metadata_df: Optional metadata for coloring.
        group_column: Column for group colors.
        
    Returns:
        Plotly figure JSON dict.
    """
    fig = go.Figure()
    
    # Plot X coordinates (reference)
    fig.add_trace(go.Scatter(
        x=coords_df["X_PC1"],
        y=coords_df["X_PC2"],
        mode="markers+text",
        name="Dataset 1",
        text=coords_df["sample"],
        textposition="top center",
        marker=dict(size=12, color="#1f77b4", symbol="circle", opacity=0.7),
        hovertemplate="<b>%{text}</b><br>PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>",
    ))
    
    # Plot Y coordinates (transformed)
    fig.add_trace(go.Scatter(
        x=coords_df["Y_PC1"],
        y=coords_df["Y_PC2"],
        mode="markers+text",
        name="Dataset 2 (Procrustes aligned)",
        text=coords_df["sample"],
        textposition="bottom center",
        marker=dict(size=12, color="#ff7f0e", symbol="diamond", opacity=0.7),
        hovertemplate="<b>%{text}</b><br>PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>",
    ))
    
    # Add connecting lines
    for _, row in coords_df.iterrows():
        fig.add_trace(go.Scatter(
            x=[row["X_PC1"], row["Y_PC1"]],
            y=[row["X_PC2"], row["Y_PC2"]],
            mode="lines",
            line=dict(color="gray", width=0.5, dash="dot"),
            showlegend=False,
            hoverinfo="skip",
        ))
    
    fig.update_layout(
        title="Procrustes Analysis: Cross-omics Comparison",
        xaxis_title="PC1",
        yaxis_title="PC2",
        template="plotly_white",
        height=500,
        width=600,
        showlegend=True,
    )
    
    return fig.to_dict()


def plotly_mantel_scatter(dist1_flat: np.ndarray, dist2_flat: np.ndarray,
                          correlation: float, p_value: float) -> dict:
    """Generate Mantel test scatter plot.
    
    Args:
        dist1_flat, dist2_flat: Flattened distance vectors.
        correlation: Correlation coefficient.
        p_value: P-value.
        
    Returns:
        Plotly figure JSON dict.
    """
    fig = go.Figure(data=go.Scatter(
        x=dist1_flat,
        y=dist2_flat,
        mode="markers",
        marker=dict(size=8, opacity=0.5, color="#2ca02c"),
        hovertemplate="Dist1: %{x:.3f}<br>Dist2: %{y:.3f}<extra></extra>",
    ))
    
    # Add regression line
    z = np.polyfit(dist1_flat, dist2_flat, 1)
    p = np.poly1d(z)
    x_line = np.linspace(dist1_flat.min(), dist1_flat.max(), 100)
    
    fig.add_trace(go.Scatter(
        x=x_line,
        y=p(x_line),
        mode="lines",
        line=dict(color="#d62728", width=2),
        name=f"r={correlation:.3f}, p={p_value:.4f}",
    ))
    
    fig.update_layout(
        title=f"Mantel Test: r={correlation:.3f}, p={p_value:.4f}",
        xaxis_title="Distance Matrix 1",
        yaxis_title="Distance Matrix 2",
        template="plotly_white",
        height=500,
        width=500,
        showlegend=True,
    )
    
    return fig.to_dict()


# ─────────────────────────────── Main Runner

def run_cross_omics_analysis(
    df1: pd.DataFrame,
    df2: Optional[pd.DataFrame] = None,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run cross-omics analysis (Procrustes and/or Mantel).

    Args:
        df1: Primary feature table (features x samples), e.g. microbiome.
        df2: Secondary feature table (features x samples), e.g. metabolome.
             If None and analysis_type requires df2, a noisy version of df1 is used for testing.
        metadata_df: Optional metadata.
        parameters: Dict with keys:
            - analysis_type: 'procrustes', 'mantel', or 'both' (default 'both')
            - procrustes_method: 'pcoa' or 'raw' (default 'pcoa')
            - mantel_metric: 'braycurtis', 'euclidean' (default 'braycurtis')
            - mantel_method: 'pearson' or 'spearman' (default 'pearson')
            - n_permutations: int (default 999)
            - group_column: metadata column for coloring

    Returns:
        Normalized dict with keys plot_data, statistics, data, and method-specific keys.
    """
    params = parameters or {}
    analysis_type = params.get("analysis_type", "both")
    procrustes_method = params.get("procrustes_method", "pcoa")
    mantel_metric = params.get("mantel_metric", "braycurtis")
    mantel_method = params.get("mantel_method", "pearson")
    n_permutations = params.get("n_permutations", 999)
    group_column = params.get("group_column")

    logger.info(
        f"Starting cross-omics analysis: type={analysis_type}, "
        f"procrustes={procrustes_method}, mantel={mantel_metric}"
    )

    # If df2 not provided, create a noisy version for testing
    if df2 is None:
        rng = np.random.RandomState(seed=42)
        noise = rng.normal(0, 0.1, df1.shape)
        df2 = df1 + noise
        df2 = df2.clip(lower=0)

    result: Dict[str, Any] = {"analysis_type": analysis_type}

    # 1. Procrustes analysis (if requested)
    if analysis_type in ("procrustes", "both"):
        procrustes_result = run_procrustes(df1, df2, method=procrustes_method)
        if "error" in procrustes_result:
            return procrustes_result

        result["procrustes"] = _sanitize_json({
            "method": procrustes_method,
            "n_common_samples": procrustes_result["n_common_samples"],
            "m2": procrustes_result["m2"],
            "normalized_m2": procrustes_result["normalized_m2"],
            "scale_factor": procrustes_result["scale_factor"],
            "coordinates": procrustes_result["coordinates"],
        })

    # 2. Mantel test (if requested)
    if analysis_type in ("mantel", "both"):
        mantel_result = run_mantel(df1, df2, metric=mantel_metric, method=mantel_method, n_permutations=n_permutations)
        result["mantel"] = _sanitize_json(mantel_result)

    # 3. Generate plots
    plots: Dict[str, Any] = {}

    if "procrustes" in result:
        coords_df = pd.DataFrame(result["procrustes"]["coordinates"])
        plots["procrustes_plot"] = plotly_procrustes(coords_df, metadata_df, group_column)

    if "mantel" in result:
        common_samples = df1.columns.intersection(df2.columns)
        dist1_matrix = squareform(pdist(df1[common_samples].T, metric=mantel_metric))
        dist2_matrix = squareform(pdist(df2[common_samples].T, metric=mantel_metric))
        n = len(common_samples)
        idx = np.triu_indices(n, k=1)
        dist1_flat = dist1_matrix[idx]
        dist2_flat = dist2_matrix[idx]
        plots["mantel_scatter"] = plotly_mantel_scatter(
            dist1_flat, dist2_flat, result["mantel"]["correlation"], result["mantel"]["p_value"]
        )

    result["plots"] = plots

    # 4. Normalize top-level output for the Agent integrator / frontend
    if analysis_type == "procrustes":
        result["plot_data"] = plots.get("procrustes_plot")
        result["statistics"] = {
            "m2": result["procrustes"]["m2"],
            "normalized_m2": result["procrustes"]["normalized_m2"],
            "scale_factor": result["procrustes"]["scale_factor"],
            "n_common_samples": result["procrustes"]["n_common_samples"],
        }
    elif analysis_type == "mantel":
        result["plot_data"] = plots.get("mantel_scatter")
        result["statistics"] = {
            "correlation": result["mantel"]["correlation"],
            "pvalue": result["mantel"]["p_value"],
            "n_permutations": result["mantel"]["n_permutations"],
            "n_common_samples": result["mantel"]["n_common_samples"],
        }
    else:
        result["plot_data"] = plots.get("procrustes_plot")
        result["statistics"] = {
            "procrustes_m2": result["procrustes"]["m2"],
            "mantel_correlation": result["mantel"]["correlation"],
            "mantel_pvalue": result["mantel"]["p_value"],
        }

    logger.info("Cross-omics analysis complete")
    return result
