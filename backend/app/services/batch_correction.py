#!/usr/bin/env python3
"""Meta2bAnalyst — Batch Effect Correction
Supports ComBat-seq, ComBat (sva) and MMUPHin via rpy2 with Python fallbacks.
"""
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── rpy2 bootstrap (same pattern as r_analysis.py) ────────────────────────
R_AVAILABLE = False
R_PACKAGES = {}
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr

    R_AVAILABLE = True
    logger.info("rpy2 available for batch correction")

    for pkg in ['sva', 'MMUPHin', 'imputeLCMD', 'missForest']:
        try:
            importr(pkg)
            R_PACKAGES[pkg] = True
            logger.info(f"R package {pkg} available")
        except Exception as e:
            R_PACKAGES[pkg] = False
            logger.warning(f"R package {pkg} not available: {e}")
except ImportError as e:
    logger.warning(f"rpy2 not installed ({e}). Batch correction will use Python fallbacks.")


def _rpackage_available(pkg: str) -> bool:
    """On-demand probe for R packages not checked at import time."""
    if pkg in R_PACKAGES:
        return R_PACKAGES[pkg]
    if not R_AVAILABLE:
        R_PACKAGES[pkg] = False
        return False
    try:
        importr(pkg)
        R_PACKAGES[pkg] = True
    except Exception:
        R_PACKAGES[pkg] = False
    return R_PACKAGES[pkg]


# ── Python fallbacks ──────────────────────────────────────────────────────

def _python_median_batch_correction(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    batch_column: str,
    biological_covariates: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Simple median-by-batch correction (Python fallback).

    For each feature, compute the median per batch, subtract the grand median,
    and add back the batch median. This removes the global batch offset while
    preserving biological variance.
    """
    common_samples = df.columns.intersection(metadata_df.index)
    df = df[common_samples].copy()
    batch = metadata_df.loc[common_samples, batch_column]

    corrected = df.copy().astype(float)
    for feature in corrected.index:
        vals = corrected.loc[feature]
        batch_medians = vals.groupby(batch).median()
        grand_median = vals.median()
        for b, med in batch_medians.items():
            mask = batch == b
            corrected.loc[feature, mask] = vals[mask] - med + grand_median

    # Ensure non-negative for count-like data
    corrected = corrected.clip(lower=0)
    logger.info("Median-by-batch correction applied (Python fallback)")
    return corrected


def _python_combat_fallback(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    batch_column: str,
    biological_covariates: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Python approximation of ComBat: location-scale batch adjustment.

    Uses a simplified mean-variance batch correction per feature.
    Not the full empirical Bayes ComBat — use only when sva is unavailable.
    """
    common_samples = df.columns.intersection(metadata_df.index)
    df = df[common_samples].copy().astype(float)
    batch = metadata_df.loc[common_samples, batch_column]

    # Optional covariate adjustment (ANOVA-style residualisation)
    if biological_covariates:
        valid_covs = [c for c in biological_covariates if c in metadata_df.columns]
        if valid_covs:
            from scipy import linalg
            design = pd.get_dummies(metadata_df.loc[common_samples, valid_covs], drop_first=True)
            design = np.column_stack([np.ones(len(design)), design.astype(float)])
            for feature in df.index:
                y = df.loc[feature].values
                beta = linalg.lstsq(design, y)[0]
                df.loc[feature] = y - design.dot(beta) + beta[0]

    corrected = df.copy()
    for feature in df.index:
        vals = df.loc[feature]
        batch_means = vals.groupby(batch).mean()
        batch_stds = vals.groupby(batch).std(ddof=1).replace(0, 1e-6)
        grand_mean = vals.mean()
        grand_std = vals.std(ddof=1).replace(0, 1e-6)

        for b in batch.unique():
            mask = batch == b
            if mask.sum() == 0:
                continue
            standardized = (vals[mask] - batch_means[b]) / batch_stds[b]
            corrected.loc[feature, mask] = standardized * grand_std + grand_mean

    corrected = corrected.clip(lower=0)
    logger.info("Location-scale batch correction applied (Python ComBat approximation)")
    return corrected


# ── R wrappers ────────────────────────────────────────────────────────────

def _run_combat_seq_r(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    batch_column: str,
    biological_covariates: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Run sva::ComBat_seq on raw integer counts."""
    common_samples = df.columns.intersection(metadata_df.index)
    count_sub = df[common_samples].astype(int)
    meta_sub = metadata_df.loc[common_samples].copy()
    batch_vec = meta_sub[batch_column].astype(str)

    # Build covariate matrix if provided
    covariate_str = "NULL"
    if biological_covariates:
        valid = [c for c in biological_covariates if c in meta_sub.columns]
        if valid:
            cov_df = pd.get_dummies(meta_sub[valid], drop_first=True)
            # Convert to R matrix string representation is tricky; pass as data.frame
            with localconverter(ro.default_converter + pandas2ri.converter):
                r_counts = ro.conversion.py2rpy(count_sub)
                r_cov = ro.conversion.py2rpy(cov_df.astype(float))
                batch_r = ro.StrVector(batch_vec.tolist())

                ro.r('''
                run_combat_seq <- function(counts, batch, covariates) {
                    library(sva)
                    if (!is.null(covariates)) {
                        corrected <- ComBat_seq(as.matrix(counts), batch=batch, covar_mod=as.matrix(covariates))
                    } else {
                        corrected <- ComBat_seq(as.matrix(counts), batch=batch)
                    }
                    return(as.data.frame(corrected))
                }
                ''')
                r_func = ro.r['run_combat_seq']
                result_r = r_func(r_counts, batch_r, r_cov)
                result_df = ro.conversion.rpy2py(result_r)
            result_df.index = count_sub.index
            result_df.columns = count_sub.columns
            return result_df.astype(float)

    with localconverter(ro.default_converter + pandas2ri.converter):
        r_counts = ro.conversion.py2rpy(count_sub)
        batch_r = ro.StrVector(batch_vec.tolist())

        ro.r('''
        run_combat_seq <- function(counts, batch) {
            library(sva)
            corrected <- ComBat_seq(as.matrix(counts), batch=batch)
            return(as.data.frame(corrected))
        }
        ''')
        r_func = ro.r['run_combat_seq']
        result_r = r_func(r_counts, batch_r)
        result_df = ro.conversion.rpy2py(result_r)

    result_df.index = count_sub.index
    result_df.columns = count_sub.columns
    return result_df.astype(float)


def _run_combat_r(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    batch_column: str,
    biological_covariates: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Run sva::ComBat on log-transformed (or continuous) data."""
    common_samples = df.columns.intersection(metadata_df.index)
    data_sub = df[common_samples].astype(float)
    meta_sub = metadata_df.loc[common_samples].copy()
    batch_vec = meta_sub[batch_column].astype(str)

    with localconverter(ro.default_converter + pandas2ri.converter):
        r_data = ro.conversion.py2rpy(data_sub)
        batch_r = ro.StrVector(batch_vec.tolist())

        # Build optional mod matrix
        if biological_covariates:
            valid = [c for c in biological_covariates if c in meta_sub.columns]
            if valid:
                cov_df = pd.get_dummies(meta_sub[valid], drop_first=True).astype(float)
                r_cov = ro.conversion.py2rpy(cov_df)
                ro.r('''
                run_combat <- function(dat, batch, covariates) {
                    library(sva)
                    mod <- model.matrix(~., data=as.data.frame(covariates))
                    corrected <- ComBat(dat=as.matrix(dat), batch=batch, mod=mod)
                    return(as.data.frame(corrected))
                }
                ''')
                r_func = ro.r['run_combat']
                result_r = r_func(r_data, batch_r, r_cov)
            else:
                ro.r('''
                run_combat <- function(dat, batch) {
                    library(sva)
                    corrected <- ComBat(dat=as.matrix(dat), batch=batch)
                    return(as.data.frame(corrected))
                }
                ''')
                r_func = ro.r['run_combat']
                result_r = r_func(r_data, batch_r)
        else:
            ro.r('''
            run_combat <- function(dat, batch) {
                library(sva)
                corrected <- ComBat(dat=as.matrix(dat), batch=batch)
                return(as.data.frame(corrected))
            }
            ''')
            r_func = ro.r['run_combat']
            result_r = r_func(r_data, batch_r)

        result_df = ro.conversion.rpy2py(result_r)

    result_df.index = data_sub.index
    result_df.columns = data_sub.columns
    return result_df.astype(float)


def _run_mmuphin_r(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    batch_column: str,
    biological_covariates: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Run MMUPHin::adjust_batch as a fallback method."""
    common_samples = df.columns.intersection(metadata_df.index)
    data_sub = df[common_samples].astype(float)
    meta_sub = metadata_df.loc[common_samples].copy()
    batch_vec = meta_sub[batch_column].astype(str)

    with localconverter(ro.default_converter + pandas2ri.converter):
        r_data = ro.conversion.py2rpy(data_sub)
        batch_r = ro.StrVector(batch_vec.tolist())

        if biological_covariates:
            valid = [c for c in biological_covariates if c in meta_sub.columns]
            if valid:
                cov_df = pd.get_dummies(meta_sub[valid], drop_first=True).astype(float)
                r_cov = ro.conversion.py2rpy(cov_df)
                ro.r('''
                run_mmuphin <- function(dat, batch, covariates) {
                    library(MMUPHin)
                    corrected <- adjust_batch(feature_abd=as.matrix(dat), batch=batch, covariates=as.data.frame(covariates))
                    return(as.data.frame(corrected$feature_abd_adj))
                }
                ''')
                r_func = ro.r['run_mmuphin']
                result_r = r_func(r_data, batch_r, r_cov)
            else:
                ro.r('''
                run_mmuphin <- function(dat, batch) {
                    library(MMUPHin)
                    corrected <- adjust_batch(feature_abd=as.matrix(dat), batch=batch)
                    return(as.data.frame(corrected$feature_abd_adj))
                }
                ''')
                r_func = ro.r['run_mmuphin']
                result_r = r_func(r_data, batch_r)
        else:
            ro.r('''
            run_mmuphin <- function(dat, batch) {
                library(MMUPHin)
                corrected <- adjust_batch(feature_abd=as.matrix(dat), batch=batch)
                return(as.data.frame(corrected$feature_abd_adj))
            }
            ''')
            r_func = ro.r['run_mmuphin']
            result_r = r_func(r_data, batch_r)

        result_df = ro.conversion.rpy2py(result_r)

    result_df.index = data_sub.index
    result_df.columns = data_sub.columns
    return result_df.astype(float)


# ── PCA / visualisation helpers ───────────────────────────────────────────

def _compute_pca(df: pd.DataFrame, n_components: int = 2) -> pd.DataFrame:
    """Return sample × PC DataFrame."""
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    X = df.T.fillna(0).astype(float).values
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    pca = PCA(n_components=n_components)
    pcs = pca.fit_transform(Xs)
    pcs_df = pd.DataFrame(
        pcs,
        index=df.columns,
        columns=[f"PC{i+1}" for i in range(n_components)],
    )
    pcs_df["explained_variance_ratio"] = list(pca.explained_variance_ratio_)
    return pcs_df


def _make_pca_plotly(
    before_pca: pd.DataFrame,
    after_pca: pd.DataFrame,
    metadata_df: pd.DataFrame,
    batch_column: str,
) -> Dict[str, Any]:
    """Return Plotly figure JSON for PCA before/after coloured by batch."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        logger.warning("plotly not available; skipping PCA plot generation")
        return {}

    batch = metadata_df.loc[before_pca.index, batch_column]
    batches = sorted(batch.unique())

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Before correction", "After correction"),
        horizontal_spacing=0.12,
    )

    colors = [
        "#E15759", "#4E79A7", "#59A14F", "#EDC948",
        "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
    ]

    for i, b in enumerate(batches):
        color = colors[i % len(colors)]
        mask_before = batch == b
        mask_after = batch.loc[after_pca.index] == b

        fig.add_trace(
            go.Scatter(
                x=before_pca.loc[mask_before, "PC1"],
                y=before_pca.loc[mask_before, "PC2"],
                mode="markers",
                name=str(b),
                marker=dict(size=10, color=color, opacity=0.8),
                legendgroup=str(b),
                showlegend=True,
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=after_pca.loc[mask_after, "PC1"],
                y=after_pca.loc[mask_after, "PC2"],
                mode="markers",
                name=str(b),
                marker=dict(size=10, color=color, opacity=0.8),
                legendgroup=str(b),
                showlegend=False,
            ),
            row=1, col=2,
        )

    fig.update_layout(
        title_text="PCA before / after batch correction",
        template="plotly_white",
        height=500,
        width=950,
    )
    fig.update_xaxes(title_text="PC1")
    fig.update_yaxes(title_text="PC2")

    return fig.to_dict()


def _make_batch_boxplots(
    before_df: pd.DataFrame,
    after_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    batch_column: str,
) -> Dict[str, Any]:
    """Boxplot of PC1 by batch before/after."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return {}

    before_pca = _compute_pca(before_df, n_components=2)
    after_pca = _compute_pca(after_df, n_components=2)

    batch_before = metadata_df.loc[before_pca.index, batch_column]
    batch_after = metadata_df.loc[after_pca.index, batch_column]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("PC1 by batch (before)", "PC1 by batch (after)"),
    )

    fig.add_trace(
        go.Box(
            x=batch_before.astype(str),
            y=before_pca["PC1"],
            name="Before",
            marker_color="#4E79A7",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Box(
            x=batch_after.astype(str),
            y=after_pca["PC1"],
            name="After",
            marker_color="#59A14F",
        ),
        row=1, col=2,
    )

    fig.update_layout(
        title_text="PC1 distribution by batch",
        template="plotly_white",
        height=450,
        width=900,
        showlegend=False,
    )
    return fig.to_dict()


# ── Public API ────────────────────────────────────────────────────────────

def run_batch_correction(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    batch_column: str,
    biological_covariates: Optional[List[str]] = None,
    method: str = "combat_seq",
    data_type: str = "microbiome",
) -> Dict[str, Any]:
    """Run batch effect correction and return corrected matrix + params + plot.

    Parameters
    ----------
    df : pd.DataFrame
        Feature × sample matrix. For ``combat_seq`` this should be raw counts;
        for ``combat`` it should be log-transformed (or continuous) data.
    metadata_df : pd.DataFrame
        Sample metadata (index = sample IDs).
    batch_column : str
        Column in ``metadata_df`` containing batch labels.
    biological_covariates : list[str], optional
        Columns to preserve during correction.
    method : {"combat_seq", "combat", "mmuphin"}
        Correction algorithm.
    data_type : str
        Hint for logging (e.g. "microbiome", "metabolome").

    Returns
    -------
    dict
        {
            "corrected_matrix": pd.DataFrame,
            "combat_params": dict,
            "plot_data": dict,   # Plotly JSON
        }
    """
    if batch_column not in metadata_df.columns:
        raise ValueError(f"batch_column '{batch_column}' not found in metadata")

    common_samples = df.columns.intersection(metadata_df.index)
    if len(common_samples) == 0:
        raise ValueError("No common samples between data matrix and metadata")

    df = df[common_samples]
    n_batches = metadata_df.loc[common_samples, batch_column].nunique()
    if n_batches < 2:
        logger.warning("Only one batch detected; returning input unchanged")
        return {
            "corrected_matrix": df.copy(),
            "combat_params": {
                "method": method,
                "engine": "none",
                "note": "Single batch — no correction applied",
                "n_features": df.shape[0],
                "n_samples": df.shape[1],
                "n_batches": n_batches,
            },
            "plot_data": {},
        }

    # ── Determine engine ──
    engine = "python"
    corrected = None
    combat_params: Dict[str, Any] = {
        "method": method,
        "data_type": data_type,
        "batch_column": batch_column,
        "biological_covariates": biological_covariates or [],
        "n_features": df.shape[0],
        "n_samples": df.shape[1],
        "n_batches": n_batches,
    }

    if method == "combat_seq":
        if R_AVAILABLE and _rpackage_available('sva'):
            try:
                corrected = _run_combat_seq_r(df, metadata_df, batch_column, biological_covariates)
                engine = "R::sva::ComBat_seq"
            except Exception as e:
                logger.error(f"ComBat_seq R failed: {e}; falling back to Python")
                corrected = _python_combat_fallback(df, metadata_df, batch_column, biological_covariates)
                engine = "python-approx::combat_seq"
        else:
            corrected = _python_combat_fallback(df, metadata_df, batch_column, biological_covariates)
            engine = "python-approx::combat_seq"

    elif method == "combat":
        if R_AVAILABLE and _rpackage_available('sva'):
            try:
                corrected = _run_combat_r(df, metadata_df, batch_column, biological_covariates)
                engine = "R::sva::ComBat"
            except Exception as e:
                logger.error(f"ComBat R failed: {e}; falling back to Python")
                corrected = _python_combat_fallback(df, metadata_df, batch_column, biological_covariates)
                engine = "python-approx::combat"
        else:
            corrected = _python_combat_fallback(df, metadata_df, batch_column, biological_covariates)
            engine = "python-approx::combat"

    elif method == "mmuphin":
        if R_AVAILABLE and _rpackage_available('MMUPHin'):
            try:
                corrected = _run_mmuphin_r(df, metadata_df, batch_column, biological_covariates)
                engine = "R::MMUPHin::adjust_batch"
            except Exception as e:
                logger.error(f"MMUPHin R failed: {e}; falling back to Python")
                corrected = _python_median_batch_correction(df, metadata_df, batch_column, biological_covariates)
                engine = "python-approx::mmuphin"
        else:
            corrected = _python_median_batch_correction(df, metadata_df, batch_column, biological_covariates)
            engine = "python-approx::mmuphin"

    else:
        raise ValueError(f"Unknown batch correction method: {method}")

    combat_params["engine"] = engine

    # ── PCA plots ──
    before_pca = _compute_pca(df, n_components=2)
    after_pca = _compute_pca(corrected, n_components=2)

    pca_plot = _make_pca_plotly(before_pca, after_pca, metadata_df, batch_column)
    box_plot = _make_batch_boxplots(df, corrected, metadata_df, batch_column)

    plot_data = {
        "pca": pca_plot,
        "pc1_boxplot": box_plot,
    }

    return {
        "corrected_matrix": corrected,
        "combat_params": combat_params,
        "plot_data": plot_data,
    }
