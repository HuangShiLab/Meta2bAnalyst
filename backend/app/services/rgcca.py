#!/usr/bin/env python3
"""Meta2bAnalyst - RGCCA Multi-Omics Integration Module

Regularized Generalized Canonical Correlation Analysis for >2 omics blocks.
Uses rpy2 to call RGCCA::rgcca when available, with a Python fallback based on
iterative multi-block CCA with optional soft-thresholding sparsity.

References:
    Tenenhaus A, Philippe C, Guillemot V, Le Cao KA, Grill J, Frouin V.
    Variable selection for generalized canonical correlation analysis.
    Biostatistics. 2014;15(3):569-83.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# ─────────────────────────────── R availability

R_AVAILABLE = False
R_RGCCA_AVAILABLE = False
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr

    R_AVAILABLE = True
    try:
        importr("RGCCA")
        R_RGCCA_AVAILABLE = True
        logger.info("R package RGCCA is available")
    except Exception as e:
        logger.warning(f"R package RGCCA not available: {e}")
except ImportError as e:
    logger.warning(f"rpy2 not installed ({e}). Using Python fallback for RGCCA.")


# ─────────────────────────────── Public API


def run_rgcca(
    blocks: dict,
    design_matrix: Optional[List[List[float]]] = None,
    sparsity: bool = True,
    n_components: int = 2,
) -> Dict[str, Any]:
    """Run RGCCA (Regularized Generalized CCA) for multi-omics integration.

    Parameters
    ----------
    blocks : dict
        Mapping ``{'microbiome': df1, 'metabolome': df2, ...}``.
        Each DataFrame must be **samples × features** and share the same
        sample IDs (row index).
    design_matrix : list[list[float]] | None
        Symmetric matrix of shape ``(n_blocks, n_blocks)`` where ``1``
        indicates associated blocks and ``0`` independent blocks.
        ``None`` defaults to a fully-connected design (all ones except diagonal).
    sparsity : bool
        If ``True``, enforce sparsity via soft-thresholding on canonical weights.
    n_components : int
        Number of global components to extract (default 2).

    Returns
    -------
    dict
        ``{"components": dict, "loadings": dict, "plot_data": dict,
        "circos": dict, "block_names": list, "n_samples": int,
        "r_engine_used": bool}``
    """
    if not blocks or len(blocks) < 2:
        raise ValueError("RGCCA requires at least 2 omics blocks.")

    if R_AVAILABLE and R_RGCCA_AVAILABLE:
        try:
            result = _run_rgcca_r(blocks, design_matrix, sparsity, n_components)
            result["r_engine_used"] = True
            return result
        except Exception as e:
            logger.error(f"RGCCA R call failed: {e}; falling back to Python")

    result = _run_rgcca_python(blocks, design_matrix, sparsity, n_components)
    result["r_engine_used"] = False
    return result


# ─────────────────────────────── R implementation


def _run_rgcca_r(
    blocks: dict,
    design_matrix: Optional[List[List[float]]],
    sparsity: bool,
    n_components: int,
) -> Dict[str, Any]:
    """Call RGCCA::rgcca via rpy2."""
    block_names = list(blocks.keys())

    # Align samples across blocks
    common_samples = None
    for df in blocks.values():
        idx = df.index if isinstance(df, pd.DataFrame) else df.columns
        common_samples = idx if common_samples is None else common_samples.intersection(idx)
    if len(common_samples) == 0:
        raise ValueError("No common samples across blocks")

    # Build C symmetric matrix in R
    n_blocks = len(block_names)
    if design_matrix is None:
        C = np.ones((n_blocks, n_blocks), dtype=float)
        np.fill_diagonal(C, 0.0)
    else:
        C = np.array(design_matrix, dtype=float)

    # tau: sparsity penalties (0 = max sparsity, 1 = ridge)
    # For RGCCA, tau is per-block. 0.1 loosely approximates sparse CCA.
    tau = [0.1 if sparsity else 1.0] * n_blocks

    with localconverter(ro.default_converter + pandas2ri.converter):
        # Send each block (samples × features) as a matrix
        r_blocks = ro.ListVector({
            name: ro.conversion.py2rpy(blocks[name].loc[common_samples].values)
            for name in block_names
        })
        r_C = ro.conversion.py2rpy(C)
        r_tau = ro.FloatVector(tau)

        ro.r("""
        run_rgcca <- function(blocks, C, tau, ncomp) {
            library(RGCCA)
            # Build list of matrices with row names for sample tracking
            block_list <- list()
            block_names <- names(blocks)
            for (i in seq_along(block_names)) {
                mat <- as.matrix(blocks[[i]])
                rownames(mat) <- paste0("S", 1:nrow(mat))
                block_list[[block_names[i]]] <- mat
            }
            Cmat <- as.matrix(C)
            res <- rgcca(
                blocks = block_list,
                connection = Cmat,
                tau = as.numeric(tau),
                ncomp = rep(as.integer(ncomp), length(block_list)),
                scheme = "horst",
                scale = TRUE,
                verbose = FALSE
            )
            # Extract scores and loadings
            scores <- lapply(res$Y, as.data.frame)
            loadings <- lapply(res$a, as.data.frame)
            list(scores = scores, loadings = loadings)
        }
        """)
        r_func = ro.r["run_rgcca"]
        result_r = r_func(r_blocks, r_C, r_tau, n_components)

        r_scores = result_r.rx2("scores")
        r_loadings = result_r.rx2("loadings")

        components = {}
        loadings = {}
        for name in block_names:
            sc = ro.conversion.rpy2py(r_scores.rx2(name))
            ld = ro.conversion.rpy2py(r_loadings.rx2(name))
            # sc may come back as DataFrame or matrix
            if hasattr(sc, "values"):
                sc = sc.values
            if hasattr(ld, "values"):
                ld = ld.values
            comp_df = pd.DataFrame(
                sc,
                index=common_samples,
                columns=[f"Comp{i+1}" for i in range(sc.shape[1])],
            )
            load_df = pd.DataFrame(
                ld,
                index=blocks[name].columns,
                columns=[f"Comp{i+1}" for i in range(ld.shape[1])],
            )
            components[name] = comp_df
            loadings[name] = load_df

    plot_data = _build_biplot(components, block_names)
    circos = _build_circos(loadings, block_names, n_components)

    return {
        "components": {k: v.to_dict() for k, v in components.items()},
        "loadings": {k: v.to_dict() for k, v in loadings.items()},
        "plot_data": plot_data,
        "circos": circos,
        "block_names": block_names,
        "n_samples": len(common_samples),
    }


# ─────────────────────────────── Python fallback


def _soft_threshold(x: np.ndarray, gamma: float) -> np.ndarray:
    """Soft-thresholding (proximal operator for L1)."""
    return np.sign(x) * np.maximum(np.abs(x) - gamma, 0.0)


def _run_rgcca_python(
    blocks: dict,
    design_matrix: Optional[List[List[float]]],
    sparsity: bool,
    n_components: int,
) -> Dict[str, Any]:
    """Python fallback: iterative multi-block CCA with optional sparsity."""
    block_names = list(blocks.keys())
    n_blocks = len(block_names)

    # Align samples
    common_samples = None
    for df in blocks.values():
        idx = df.index if isinstance(df, pd.DataFrame) else df.columns
        common_samples = idx if common_samples is None else common_samples.intersection(idx)
    if len(common_samples) == 0:
        raise ValueError("No common samples across blocks")

    # Extract aligned matrices (samples × features)
    Xs = []
    feature_names = []
    for name in block_names:
        df = blocks[name].loc[common_samples]
        X = df.values.astype(float)
        # Remove zero-variance columns
        var_mask = X.std(axis=0) > 0
        X = X[:, var_mask]
        Xs.append(X)
        feature_names.append(df.columns[var_mask].tolist())

    # Standardize each block
    Xs_std = [StandardScaler().fit_transform(X) for X in Xs]

    # Design matrix
    if design_matrix is None:
        C = np.ones((n_blocks, n_blocks), dtype=float)
        np.fill_diagonal(C, 0.0)
    else:
        C = np.array(design_matrix, dtype=float)

    n_samples = len(common_samples)
    pjs = [X.shape[1] for X in Xs_std]

    # Storage for all components
    all_scores = {name: [] for name in block_names}
    all_loadings = {name: [] for name in block_names}

    # Working copies for deflation
    X_work = [X.copy() for X in Xs_std]

    for comp in range(n_components):
        # Initialize weights randomly
        a = [np.random.randn(pj) for pj in pjs]
        for j in range(n_blocks):
            norm = np.linalg.norm(a[j])
            if norm > 0:
                a[j] = a[j] / norm

        # Iterative power method (Horst scheme)
        max_iter = 200
        tol = 1e-6
        lr = 0.05
        for it in range(max_iter):
            a_old = [aj.copy() for aj in a]
            for j in range(n_blocks):
                # Y_j = sum_{k != j} C[j,k] * X_k @ a_k
                y = np.zeros(n_samples)
                for k in range(n_blocks):
                    if C[j, k] != 0 and j != k:
                        y += C[j, k] * (X_work[k] @ a[k])
                # Update
                grad = X_work[j].T @ y / n_samples
                aj_new = a[j] + lr * grad
                # Sparsity
                if sparsity:
                    # Adaptive gamma based on percentile
                    gamma = np.percentile(np.abs(aj_new), 70)
                    aj_new = _soft_threshold(aj_new, gamma)
                # Normalize
                norm = np.linalg.norm(aj_new)
                if norm > 0:
                    aj_new = aj_new / norm
                a[j] = aj_new

            delta = sum(np.linalg.norm(a[j] - a_old[j]) for j in range(n_blocks))
            if delta < tol:
                break

        # Record scores and loadings
        for j, name in enumerate(block_names):
            tj = X_work[j] @ a[j]
            all_scores[name].append(tj)
            all_loadings[name].append(a[j])

        # Deflation: remove the component from each block
        for j in range(n_blocks):
            tj = X_work[j] @ a[j]
            # Project out
            tj_norm = tj @ tj
            if tj_norm > 1e-12:
                X_work[j] = X_work[j] - np.outer(tj, tj @ X_work[j]) / tj_norm

    # Assemble DataFrames
    components = {}
    loadings = {}
    for j, name in enumerate(block_names):
        comp_mat = np.column_stack(all_scores[name])
        load_mat = np.column_stack(all_loadings[name])
        components[name] = pd.DataFrame(
            comp_mat,
            index=common_samples,
            columns=[f"Comp{i+1}" for i in range(n_components)],
        )
        loadings[name] = pd.DataFrame(
            load_mat,
            index=feature_names[j],
            columns=[f"Comp{i+1}" for i in range(n_components)],
        )

    plot_data = _build_biplot(components, block_names)
    circos = _build_circos(loadings, block_names, n_components)

    return {
        "components": {k: v.to_dict() for k, v in components.items()},
        "loadings": {k: v.to_dict() for k, v in loadings.items()},
        "plot_data": plot_data,
        "circos": circos,
        "block_names": block_names,
        "n_samples": len(common_samples),
    }


# ─────────────────────────────── Plotly visualisations


def _build_biplot(
    components: Dict[str, pd.DataFrame],
    block_names: List[str],
) -> Dict[str, Any]:
    """Build a 2D biplot of sample scores for the first two components."""
    colors = [
        "#1f77b4",  # blue
        "#ff7f0e",  # orange
        "#2ca02c",  # green
        "#d62728",  # red
        "#9467bd",  # purple
        "#8c564b",  # brown
    ]

    fig = go.Figure()
    for idx, name in enumerate(block_names):
        df = components[name]
        x = df["Comp1"].values
        y = df["Comp2"].values if "Comp2" in df.columns else np.zeros_like(x)
        color = colors[idx % len(colors)]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="markers",
                name=name,
                marker=dict(size=10, color=color, opacity=0.8, line=dict(width=1, color="white")),
                text=df.index,
                hovertemplate=f"<b>{name}</b><br>%{{text}}<br>Comp1: %{{x:.3f}}<br>Comp2: %{{y:.3f}}<extra></extra>",
            )
        )

    fig.update_layout(
        title="RGCCA Sample Scores Biplot (Comp 1 vs Comp 2)",
        xaxis_title="Component 1",
        yaxis_title="Component 2",
        template="plotly_white",
        height=550,
        width=650,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
        hovermode="closest",
    )
    return fig.to_dict()


def _build_circos(
    loadings: Dict[str, pd.DataFrame],
    block_names: List[str],
    n_components: int,
) -> Dict[str, Any]:
    """Build a circos-style correlation circle for feature loadings.

    Features from each block are arranged in angular sectors around a unit
    circle.  The radial distance from the origin encodes the L2 norm of the
    loading vector (strength of association with the global components).
    """
    # Select top N features per block to keep the plot readable
    top_n = 40

    fig = go.Figure()
    colors = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
    ]

    # Draw unit circle reference
    theta = np.linspace(0, 2 * np.pi, 200)
    fig.add_trace(
        go.Scatter(
            x=np.cos(theta),
            y=np.sin(theta),
            mode="lines",
            line=dict(color="#94a3b8", width=1, dash="dot"),
            name="Unit circle",
            hoverinfo="skip",
        )
    )

    # Angular sector per block
    sector_size = 2 * np.pi / len(block_names)

    for b_idx, name in enumerate(block_names):
        ld = loadings[name]
        # L2 norm of loadings across components
        norms = np.linalg.norm(ld.values, axis=1)
        # Top features
        if len(norms) > top_n:
            top_idx = np.argsort(-norms)[:top_n]
        else:
            top_idx = np.arange(len(norms))

        feat_names = ld.index[top_idx]
        feat_norms = norms[top_idx]
        feat_loadings = ld.values[top_idx, :2] if ld.shape[1] >= 2 else np.column_stack([ld.values[top_idx, 0], np.zeros(len(top_idx))])

        # Angular positions: spread within this block's sector
        n_feat = len(feat_names)
        angles = np.linspace(
            b_idx * sector_size + 0.05,
            (b_idx + 1) * sector_size - 0.05,
            n_feat,
        )

        color = colors[b_idx % len(colors)]

        # Radial distance = loading norm (clamp to [0,1.2] for visibility)
        radii = np.clip(feat_norms, 0, 1.2)

        # Convert polar → cartesian
        xs = radii * np.cos(angles)
        ys = radii * np.sin(angles)

        # Add radial spokes (origin to point)
        for i in range(n_feat):
            fig.add_trace(
                go.Scatter(
                    x=[0, xs[i]],
                    y=[0, ys[i]],
                    mode="lines",
                    line=dict(color=color, width=0.5),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

        # Add feature points
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers+text",
                name=name,
                text=[str(f) for f in feat_names],
                textposition="top center",
                textfont=dict(size=7, color=color),
                marker=dict(
                    size=6 + 8 * (radii / (radii.max() + 1e-6)),
                    color=color,
                    opacity=0.85,
                    line=dict(width=0.5, color="white"),
                ),
                hovertemplate="<b>%{text}</b><br>Block: "
                + name
                + "<br>Loading norm: %{marker.size:.2f}<extra></extra>",
            )
        )

    fig.update_layout(
        title="RGCCA Circos-Style Loading Circle",
        xaxis=dict(
            showgrid=False,
            zeroline=True,
            zerolinecolor="#cbd5e1",
            zerolinewidth=1,
            showticklabels=False,
            scaleanchor="y",
            scaleratio=1,
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=True,
            zerolinecolor="#cbd5e1",
            zerolinewidth=1,
            showticklabels=False,
        ),
        template="plotly_white",
        height=650,
        width=650,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        margin=dict(l=40, r=40, t=60, b=60),
    )
    return fig.to_dict()
