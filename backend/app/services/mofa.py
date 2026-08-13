"""
MOFA+ Multi-Omics Factor Analysis Backend Service
==================================================
Pure Python implementation of MOFA+-style joint factor analysis using sklearn.

Author: Meta2B Analyst Team
"""

import json
from typing import Any, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


def _clr_transform(df: pd.DataFrame, pseudo_count: float = 1e-6) -> pd.DataFrame:
    """
    Centered Log-Ratio (CLR) transformation for compositional data (microbiome).

    Parameters
    ----------
    df : pd.DataFrame
        Samples × features raw count / relative abundance matrix.
    pseudo_count : float
        Small constant added to avoid log(0).

    Returns
    -------
    pd.DataFrame
        CLR-transformed matrix with same shape and index/columns.
    """
    # Ensure non-negative values
    vals = df.values.astype(float)
    vals = np.where(vals < 0, 0, vals)
    vals = vals + pseudo_count
    # Geometric mean per sample (row)
    log_vals = np.log(vals)
    gm = log_vals.mean(axis=1, keepdims=True)
    clr = log_vals - gm
    return pd.DataFrame(clr, index=df.index, columns=df.columns)


def _log1p_transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Natural log(1 + x) transformation for metabolome data.

    Parameters
    ----------
    df : pd.DataFrame
        Samples × features metabolome matrix.

    Returns
    -------
    pd.DataFrame
        Log1p-transformed matrix with same shape and index/columns.
    """
    vals = df.values.astype(float)
    vals = np.where(vals < 0, 0, vals)
    return pd.DataFrame(np.log1p(vals), index=df.index, columns=df.columns)


def _compute_layer_variance_explained(
    layer_df: pd.DataFrame,
    factor_scores: np.ndarray,
    n_factors: int,
) -> np.ndarray:
    """
    Compute variance explained in a single omics layer by each factor.

    Uses the coefficient of determination (R²) per factor by regressing
    each feature on the factor scores.

    Parameters
    ----------
    layer_df : pd.DataFrame
        Samples × features matrix for one omics layer.
    factor_scores : np.ndarray
        Samples × n_factors array of latent factor scores.
    n_factors : int
        Number of factors.

    Returns
    -------
    np.ndarray
        Shape (n_factors,) — variance explained ratio per factor for this layer.
    """
    X = layer_df.values.astype(float)
    # Center each feature
    X = X - X.mean(axis=0, keepdims=True)
    total_var = np.sum(X ** 2)
    if total_var == 0:
        return np.zeros(n_factors)

    var_explained = np.zeros(n_factors)
    for k in range(n_factors):
        fk = factor_scores[:, k].reshape(-1, 1)  # (n_samples, 1)
        # OLS: beta = (f'f)^{-1} f' X  →  (1, n_features)
        beta = np.linalg.lstsq(fk, X, rcond=None)[0]
        # Predicted X from factor k alone
        X_pred = fk @ beta
        var_explained[k] = np.sum(X_pred ** 2)

    return var_explained / total_var


def run_mofa_plus(
    microbiome_df: pd.DataFrame,
    metabolome_df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    n_factors: int = 5,
    group_column: Optional[str] = None,
) -> dict[str, Any]:
    """
    Run MOFA+ style multi-omics factor analysis.

    This pure-Python implementation concatenates CLR-transformed microbiome
    and log1p-transformed metabolome data, runs PCA on the joint matrix to
    extract latent factors, and produces interactive Plotly visualisations
    together with summary statistics.

    Parameters
    ----------
    microbiome_df : pd.DataFrame
        Samples × features microbiome matrix (already filtered to common
        samples).  Will be CLR-transformed internally.
    metabolome_df : pd.DataFrame
        Samples × features metabolome matrix (already filtered to common
        samples).  Will be log1p-transformed internally.
    metadata_df : pd.DataFrame, optional
        Sample metadata DataFrame indexed by sample ID.  Used for colouring
        scatter plots when ``group_column`` is provided.
    n_factors : int, default 5
        Number of latent factors to extract.
    group_column : str, optional
        Column name in ``metadata_df`` used to colour the factor scatter plot.

    Returns
    -------
    dict
        {
            "plot_data": {
                "factor_scatter":    <Plotly JSON>,
                "variance_explained": <Plotly JSON>,
                "loading_heatmap":   <Plotly JSON>,
            },
            "statistics": {
                "n_factors": int,
                "n_samples": int,
                "n_microbiome_features": int,
                "n_metabolome_features": int,
                "variance_explained_ratio": list[float],
                "top_features_per_factor": dict[str, dict[str, list[str]]],
            }
        }
    """
    # ------------------------------------------------------------------
    # 1. Basic validation & alignment
    # ------------------------------------------------------------------
    if microbiome_df.empty or metabolome_df.empty:
        raise ValueError("microbiome_df and metabolome_df must be non-empty.")

    common_samples = microbiome_df.index.intersection(metabolome_df.index)
    if len(common_samples) == 0:
        raise ValueError(
            "No common samples between microbiome and metabolome data."
        )

    mb = microbiome_df.loc[common_samples].copy()
    mt = metabolome_df.loc[common_samples].copy()

    if metadata_df is not None:
        meta = metadata_df.loc[metadata_df.index.intersection(common_samples)].copy()
    else:
        meta = None

    n_samples = len(common_samples)
    n_mb_features = mb.shape[1]
    n_mt_features = mt.shape[1]

    # Clamp n_factors to feasible range
    max_factors = min(n_samples, n_mb_features + n_mt_features)
    n_factors = max(1, min(n_factors, max_factors))

    # ------------------------------------------------------------------
    # 2. Per-layer transformation
    # ------------------------------------------------------------------
    mb_clr = _clr_transform(mb)
    mt_log = _log1p_transform(mt)

    # ------------------------------------------------------------------
    # 3. Joint matrix → PCA
    # ------------------------------------------------------------------
    # Scale each omics layer to unit variance so neither dominates
    mb_scaled = StandardScaler().fit_transform(mb_clr.values)
    mt_scaled = StandardScaler().fit_transform(mt_log.values)

    # Concatenate horizontally: samples × (mb_features + mt_features)
    joint = np.hstack([mb_scaled, mt_scaled])

    pca = PCA(n_components=n_factors, random_state=42)
    factor_scores = pca.fit_transform(joint)  # (n_samples, n_factors)

    # Factor loadings per layer (transpose of components)
    # components_ shape: (n_factors, n_features_total)
    loadings_mb = pca.components_[:, :n_mb_features]       # (n_factors, n_mb_features)
    loadings_mt = pca.components_[:, n_mb_features:]       # (n_factors, n_mt_features)

    # Overall variance explained ratio (from sklearn)
    total_var_ratio = pca.explained_variance_ratio_.tolist()

    # ------------------------------------------------------------------
    # 4. Per-layer variance explained
    # ------------------------------------------------------------------
    mb_var_explained = _compute_layer_variance_explained(
        mb_clr, factor_scores, n_factors
    )
    mt_var_explained = _compute_layer_variance_explained(
        mt_log, factor_scores, n_factors
    )

    # ------------------------------------------------------------------
    # 5. Top features per factor
    # ------------------------------------------------------------------
    n_top = min(10, max(n_mb_features, n_mt_features))
    top_features: dict[str, dict[str, list[str]]] = {}

    for k in range(n_factors):
        # Microbiome
        mb_order = np.argsort(-np.abs(loadings_mb[k]))[:n_top]
        mb_top = mb_clr.columns[mb_order].tolist()
        # Metabolome
        mt_order = np.argsort(-np.abs(loadings_mt[k]))[:n_top]
        mt_top = mt_log.columns[mt_order].tolist()

        top_features[f"Factor{k + 1}"] = {
            "microbiome": mb_top,
            "metabolome": mt_top,
        }

    # ------------------------------------------------------------------
    # 6. Plot 1 — Factor Scatter (Factor 1 vs Factor 2)
    # ------------------------------------------------------------------
    scatter_df = pd.DataFrame(
        factor_scores[:, :2],
        index=common_samples,
        columns=["Factor1", "Factor2"],
    )

    if meta is not None and group_column and group_column in meta.columns:
        scatter_df[group_column] = meta.loc[scatter_df.index, group_column]
        fig_scatter = px.scatter(
            scatter_df.reset_index(),
            x="Factor1",
            y="Factor2",
            color=group_column,
            hover_name="index",
            title="MOFA+ Factor Scatter — Factor 1 vs Factor 2",
            labels={"Factor1": "Factor 1", "Factor2": "Factor 2"},
            template="plotly_white",
        )
    else:
        fig_scatter = px.scatter(
            scatter_df.reset_index(),
            x="Factor1",
            y="Factor2",
            hover_name="index",
            title="MOFA+ Factor Scatter — Factor 1 vs Factor 2",
            labels={"Factor1": "Factor 1", "Factor2": "Factor 2"},
            template="plotly_white",
            color_discrete_sequence=["#2E86AB"],
        )

    fig_scatter.update_traces(marker=dict(size=10, opacity=0.8, line=dict(width=1, color="DarkSlateGrey")))
    fig_scatter.update_layout(
        width=700,
        height=550,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
    )

    # ------------------------------------------------------------------
    # 7. Plot 2 — Variance Explained Bar Chart
    # ------------------------------------------------------------------
    factors = [f"Factor {i + 1}" for i in range(n_factors)]

    fig_variance = go.Figure()
    fig_variance.add_trace(
        go.Bar(
            name="Microbiome",
            x=factors,
            y=mb_var_explained.tolist(),
            marker_color="#2E86AB",
        )
    )
    fig_variance.add_trace(
        go.Bar(
            name="Metabolome",
            x=factors,
            y=mt_var_explained.tolist(),
            marker_color="#A23B72",
        )
    )
    fig_variance.update_layout(
        barmode="group",
        title="Variance Explained per Factor by Omics Layer",
        xaxis_title="Factor",
        yaxis_title="Variance Explained Ratio",
        template="plotly_white",
        width=700,
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
    )

    # ------------------------------------------------------------------
    # 8. Plot 3 — Loading Heatmap (top features only)
    # ------------------------------------------------------------------
    n_heatmap = min(15, n_mb_features, n_mt_features)
    if n_heatmap > 0:
        # Collect top features across all factors for a compact heatmap
        mb_selected = set()
        mt_selected = set()
        for k in range(n_factors):
            mb_order = np.argsort(-np.abs(loadings_mb[k]))[:n_heatmap]
            mt_order = np.argsort(-np.abs(loadings_mt[k]))[:n_heatmap]
            mb_selected.update(mb_clr.columns[mb_order])
            mt_selected.update(mt_log.columns[mt_order])

        mb_cols = list(mb_selected)[:n_heatmap]
        mt_cols = list(mt_selected)[:n_heatmap]

        # Build combined loading matrix: factors × (mb_cols + mt_cols)
        combined_loadings = np.vstack(
            [
                loadings_mb[:, [list(mb_clr.columns).index(c) for c in mb_cols]],
                loadings_mt[:, [list(mt_log.columns).index(c) for c in mt_cols]],
            ]
        ).T  # shape: (len(mb_cols)+len(mt_cols), n_factors)

        heat_labels = [f"[MB] {c}" for c in mb_cols] + [f"[MT] {c}" for c in mt_cols]
        heat_factors = [f"Factor {i + 1}" for i in range(n_factors)]

        fig_heatmap = go.Figure(
            data=go.Heatmap(
                z=combined_loadings,
                x=heat_factors,
                y=heat_labels,
                colorscale="RdBu_r",
                zmid=0,
                colorbar=dict(title="Loading"),
            )
        )
        fig_heatmap.update_layout(
            title="Top Feature Loadings per Factor",
            xaxis_title="Factor",
            yaxis_title="Feature",
            template="plotly_white",
            width=700,
            height=max(400, 25 * len(heat_labels)),
        )
    else:
        fig_heatmap = go.Figure().update_layout(
            title="Loading Heatmap — insufficient features",
            template="plotly_white",
        )

    # ------------------------------------------------------------------
    # 9. Assemble return payload
    # ------------------------------------------------------------------
    result = {
        "plot_data": {
            "factor_scatter": json.loads(fig_scatter.to_json()),
            "variance_explained": json.loads(fig_variance.to_json()),
            "loading_heatmap": json.loads(fig_heatmap.to_json()),
        },
        "statistics": {
            "n_factors": n_factors,
            "n_samples": n_samples,
            "n_microbiome_features": n_mb_features,
            "n_metabolome_features": n_mt_features,
            "variance_explained_ratio": total_var_ratio,
            "top_features_per_factor": top_features,
        },
    }

    return result
