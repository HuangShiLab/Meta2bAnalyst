"""
Meta2bAnalyst - MEFISTO Backend Service
========================================
Spatiotemporal extension of MOFA+ for longitudinal multi-omics.

MEFISTO (MOFA with Flexible time-aware factor inference) integrates
multiple omics layers while accounting for continuous covariates such
as time and spatial coordinates.  This module provides:

1. rpy2 bridge to the R/MOFA2 MEFISTO implementation (if available).
2. Pure-Python fallback: per-block PCA → joint factorisation →
   GAM-style spline regression on time for each factor.

References
----------
- Velten et al. 2022, Nature Methods 19, 199–206.
- MOFA2: https://github.com/bioFAM/MOFA2

Author: Meta2b Analyst Team
"""

import json
import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler

logger = logging.getLogger(__name__)

# ─────────────────────────────── R availability probe
R_AVAILABLE = False
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr

    R_AVAILABLE = True
    logger.info("rpy2 available in mefisto module")
except ImportError:
    logger.warning(
        "rpy2 not installed; MEFISTO will use the pure-Python PCA+GAM fallback."
    )


# ─────────────────────────────── Helpers

def _clr_transform(df: pd.DataFrame, pseudo_count: float = 1e-6) -> pd.DataFrame:
    """Centered Log-Ratio (CLR) transformation for compositional data."""
    vals = df.values.astype(float)
    vals = np.where(vals < 0, 0, vals)
    vals = vals + pseudo_count
    log_vals = np.log(vals)
    gm = log_vals.mean(axis=1, keepdims=True)
    clr = log_vals - gm
    return pd.DataFrame(clr, index=df.index, columns=df.columns)


def _log1p_transform(df: pd.DataFrame) -> pd.DataFrame:
    """Natural log(1 + x) transformation."""
    vals = df.values.astype(float)
    vals = np.where(vals < 0, 0, vals)
    return pd.DataFrame(np.log1p(vals), index=df.index, columns=df.columns)


def _block_transform(blocks: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Apply layer-appropriate transforms to each omics block."""
    transformed: Dict[str, pd.DataFrame] = {}
    for name, df in blocks.items():
        key = name.lower()
        if "microbiome" in key or "16s" in key or "tax" in key:
            transformed[name] = _clr_transform(df)
        elif "metabolome" in key or "metab" in key or "lcms" in key:
            transformed[name] = _log1p_transform(df)
        else:
            # Default: standardise
            vals = StandardScaler().fit_transform(df.values.astype(float))
            transformed[name] = pd.DataFrame(vals, index=df.index, columns=df.columns)
    return transformed


def _pca_per_block(
    blocks: Dict[str, pd.DataFrame],
    n_components: int,
    random_state: int = 42,
) -> np.ndarray:
    """
    Run PCA per block, concatenate scores, then PCA again on the joint scores.

    Returns
    -------
    factor_scores : np.ndarray, shape (n_samples, n_components)
    """
    sample_ids = None
    score_list = []
    for name, df in blocks.items():
        if sample_ids is None:
            sample_ids = df.index.tolist()
        # Reindex to common samples (already aligned upstream, but defensive)
        df = df.loc[df.index.intersection(sample_ids)]
        n_comp = min(n_components, df.shape[0] - 1, df.shape[1])
        if n_comp <= 0:
            continue
        pca = PCA(n_components=n_comp, random_state=random_state)
        scores = pca.fit_transform(df.values)  # (n_samples, n_comp)
        score_list.append(scores)

    if not score_list:
        raise ValueError("No valid omics blocks after transformation.")

    joint_scores = np.hstack(score_list)
    n_comp = min(n_components, joint_scores.shape[0] - 1, joint_scores.shape[1])
    if n_comp <= 0:
        n_comp = 1
    pca_joint = PCA(n_components=n_comp, random_state=random_state)
    factor_scores = pca_joint.fit_transform(joint_scores)
    return factor_scores


def _fit_gam_time_trend(
    time_vec: np.ndarray,
    y_vec: np.ndarray,
    smoothness: float = 0.5,
) -> Dict[str, Any]:
    """
    Fit a smooth spline (GAM-style) to y ~ s(time) using sklearn.

    Parameters
    ----------
    time_vec : np.ndarray
        1-D array of time points.
    y_vec : np.ndarray
        1-D response array (factor scores).
    smoothness : float
        Controls spline flexibility.  Maps to ``n_knots`` in
        ``SplineTransformer`` (higher → more knots → wigglier).

    Returns
    -------
    dict with ``pred_time``, ``pred_y``, ``r2``.
    """
    # Clamp smoothness to a sensible range and map to n_knots
    smoothness = float(np.clip(smoothness, 0.01, 1.0))
    # smoothness 0.01 → 3 knots, 1.0 → 12 knots
    n_knots = int(np.round(3 + 9 * smoothness))
    degree = min(3, n_knots - 1)

    X = time_vec.reshape(-1, 1)

    pipeline = make_pipeline(
        SplineTransformer(n_knots=n_knots, degree=degree, include_bias=False),
        Ridge(alpha=1e-4, fit_intercept=True),
    )
    pipeline.fit(X, y_vec)
    y_pred = pipeline.predict(X)
    ss_res = np.sum((y_vec - y_pred) ** 2)
    ss_tot = np.sum((y_vec - y_vec.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Dense prediction curve for plotting
    t_min, t_max = time_vec.min(), time_vec.max()
    t_grid = np.linspace(t_min, t_max, 200)
    y_grid = pipeline.predict(t_grid.reshape(-1, 1))

    return {
        "pred_time": t_grid,
        "pred_y": y_grid,
        "r2": float(r2),
        "n_knots": n_knots,
    }


def _mefisto_r(
    blocks: Dict[str, pd.DataFrame],
    metadata_df: pd.DataFrame,
    time_column: str,
    subject_column: str,
    n_factors: int = 5,
    smoothness: float = 0.5,
) -> Optional[Dict[str, Any]]:
    """Run MEFISTO through MOFA2::run_mofa (R).  Returns None on any failure."""
    if not R_AVAILABLE:
        return None

    try:
        importr("MOFA2")
    except Exception as e:
        logger.warning(f"MOFA2 R package not available: {e}")
        return None

    # MOFA2 expects features x samples for each block
    try:
        common_samples = None
        for df in blocks.values():
            if common_samples is None:
                common_samples = set(df.index)
            else:
                common_samples &= set(df.index)
        common_samples = sorted(common_samples)
        if len(common_samples) == 0:
            raise ValueError("No common samples across blocks.")

        # Ensure metadata covers common samples
        meta = metadata_df.loc[metadata_df.index.intersection(common_samples)].copy()
        meta = meta.loc[~meta.index.duplicated(keep="first")]
        missing_meta = set(common_samples) - set(meta.index)
        if missing_meta:
            logger.warning(
                f"Dropping {len(missing_meta)} samples missing from metadata."
            )
            common_samples = [s for s in common_samples if s not in missing_meta]
        if len(common_samples) < 3:
            raise ValueError("Need >= 3 samples with metadata.")

        # Subset blocks
        r_blocks = {}
        for name, df in blocks.items():
            sub = df.loc[df.index.intersection(common_samples)]
            # MOFA2 convention: features x samples
            r_blocks[name] = sub.T

        with localconverter(ro.default_converter + pandas2ri.converter):
            r_data_list = ro.ListVector(
                {k: ro.conversion.py2rpy(v) for k, v in r_blocks.items()}
            )
            r_meta = ro.conversion.py2rpy(meta.reset_index())

            ro.r("""
            run_mefisto <- function(data_list, metadata, time_col, subject_col,
                                    n_factors, smoothness) {
                library(MOFA2)
                # Build MOFA object
                mofa <- create_mofa_object(data_list)
                # Set metadata
                metadata <- as.data.frame(metadata)
                colnames(metadata)[1] <- "sample"
                samples_metadata(mofa) <- metadata
                # Set data options
                data_opts <- get_default_data_options(mofa)
                # Set model options
                model_opts <- get_default_model_options(mofa)
                model_opts$num_factors <- as.integer(n_factors)
                # Set training options
                train_opts <- get_default_training_options(mofa)
                # Set MEFISTO options
                mefisto_opts <- get_default_mefisto_options(mofa)
                mefisto_opts$warping <- FALSE
                mefisto_opts$model_groups <- FALSE
                mefisto_opts$n_grid <- as.integer(20)
                # Use time column as covariate
                covariates <- metadata[, time_col, drop = FALSE]
                rownames(covariates) <- metadata$sample
                samples_covariates(mofa) <- covariates
                # Prepare and train
                mofa <- prepare_mofa(mofa,
                                     data_options = data_opts,
                                     model_options = model_opts,
                                     training_options = train_opts,
                                     mefisto_options = mefisto_opts)
                mofa <- run_mofa(mofa)
                # Extract factors
                factors <- get_factors(mofa)[[1]]
                # Variance explained
                r2 <- calculate_variance_explained(mofa)
                return(list(
                    factors = as.data.frame(factors),
                    r2 = r2
                ))
            }
            """)
            r_func = ro.r["run_mefisto"]
            result_r = r_func(
                r_data_list,
                r_meta,
                time_column,
                subject_column,
                int(n_factors),
                float(smoothness),
            )
            factors_df = ro.conversion.rpy2py(result_r.rx2("factors"))
            r2_obj = result_r.rx2("r2")
            # r2 is a list of matrices per group; extract the first group
            r2_mat = ro.conversion.rpy2py(r2_obj[0])

        # Convert to tidy format
        if not isinstance(factors_df, pd.DataFrame):
            factors_df = pd.DataFrame(factors_df)
        factors_df.index = common_samples[: len(factors_df)]
        factors_df.columns = [f"Factor{i + 1}" for i in range(factors_df.shape[1])]

        # Convert r2_mat (views × factors) to dict
        if isinstance(r2_mat, np.ndarray):
            view_names = list(blocks.keys())
            r2_dict: Dict[str, Dict[str, float]] = {}
            for v_idx, view in enumerate(view_names[: r2_mat.shape[0]]):
                r2_dict[view] = {}
                for f_idx in range(r2_mat.shape[1]):
                    r2_dict[view][f"Factor{f_idx + 1}"] = float(r2_mat[v_idx, f_idx])
        else:
            r2_dict = {"R_output": str(r2_mat)}

        return {"factors": factors_df, "r2_dict": r2_dict, "engine": "R::MOFA2"}
    except Exception as e:
        logger.warning(f"MEFISTO R execution failed: {e}")
        return None


def _mefisto_python_fallback(
    blocks: Dict[str, pd.DataFrame],
    metadata_df: pd.DataFrame,
    time_column: str,
    subject_column: str,
    n_factors: int = 5,
    smoothness: float = 0.5,
) -> Dict[str, Any]:
    """
    Pure-Python MEFISTO approximation.

    Steps
    -----
    1. Per-block transform + PCA.
    2. Joint PCA across all blocks → factor scores.
    3. For each factor, fit a smooth spline against time.
    4. Compute per-block variance explained per factor.
    """
    # -- 1. Align samples -------------------------------------------------
    common_samples = None
    for df in blocks.values():
        if common_samples is None:
            common_samples = set(df.index)
        else:
            common_samples &= set(df.index)
    common_samples = sorted(common_samples)
    if len(common_samples) == 0:
        raise ValueError("No common samples across omics blocks.")

    # Metadata alignment
    meta = metadata_df.loc[metadata_df.index.intersection(common_samples)].copy()
    meta = meta.loc[~meta.index.duplicated(keep="first")]
    missing_meta = set(common_samples) - set(meta.index)
    if missing_meta:
        logger.warning(
            f"Dropping {len(missing_meta)} samples missing from metadata."
        )
        common_samples = [s for s in common_samples if s not in missing_meta]
    if len(common_samples) < 3:
        raise ValueError("Need >= 3 samples with metadata.")

    if time_column not in meta.columns:
        raise ValueError(f"time_column '{time_column}' not found in metadata.")
    if subject_column not in meta.columns:
        raise ValueError(f"subject_column '{subject_column}' not found in metadata.")

    # -- 2. Transform & factorise -----------------------------------------
    blocks_aligned = {
        k: v.loc[v.index.intersection(common_samples)]
        for k, v in blocks.items()
    }
    blocks_tf = _block_transform(blocks_aligned)
    factor_scores = _pca_per_block(blocks_tf, n_components=n_factors)
    n_factors_actual = factor_scores.shape[1]

    factors_df = pd.DataFrame(
        factor_scores,
        index=common_samples,
        columns=[f"Factor{i + 1}" for i in range(n_factors_actual)],
    )

    # -- 3. Time trends (GAM) ---------------------------------------------
    time_vals = pd.to_numeric(meta.loc[common_samples, time_column], errors="coerce")
    if time_vals.isna().all():
        raise ValueError(
            f"time_column '{time_column}' could not be coerced to numeric."
        )

    # Merge time into factors_df (same index order)
    factors_df[time_column] = time_vals.reindex(factors_df.index)

    time_trend_plots = []
    trend_stats = []
    for k in range(n_factors_actual):
        factor_name = f"Factor{k + 1}"
        sub = factors_df[[factor_name, time_column]].dropna()
        if len(sub) < 3:
            continue
        t = sub[time_column].values.astype(float)
        y = sub[factor_name].values.astype(float)
        gam = _fit_gam_time_trend(t, y, smoothness=smoothness)

        fig = go.Figure()
        # Raw points
        fig.add_trace(
            go.Scatter(
                x=t,
                y=y,
                mode="markers",
                name="Observed",
                marker=dict(size=8, opacity=0.6, color="#2E86AB"),
                hovertemplate="Time: %{x:.2f}<br>Score: %{y:.3f}<extra></extra>",
            )
        )
        # Spline
        fig.add_trace(
            go.Scatter(
                x=gam["pred_time"],
                y=gam["pred_y"],
                mode="lines",
                name=f"Spline (R²={gam['r2']:.3f})",
                line=dict(color="#A23B72", width=2.5),
            )
        )
        fig.update_layout(
            title=f"{factor_name} Time Trend",
            xaxis_title=time_column,
            yaxis_title=factor_name,
            template="plotly_white",
            width=550,
            height=400,
            showlegend=True,
            legend=dict(
                orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5
            ),
        )
        time_trend_plots.append({"factor": factor_name, "plot": fig.to_dict()})
        trend_stats.append(
            {
                "factor": factor_name,
                "r2": gam["r2"],
                "n_knots": gam["n_knots"],
                "n_obs": len(sub),
            }
        )

    # -- 4. Variance explained per block ----------------------------------
    variance_explained: Dict[str, Dict[str, float]] = {}
    total_var_all = 0.0
    for block_name, df in blocks_tf.items():
        X = df.values.astype(float)
        X = X - X.mean(axis=0, keepdims=True)
        total_var = float(np.sum(X ** 2))
        total_var_all += total_var
        block_r2 = {}
        for k in range(n_factors_actual):
            fk = factor_scores[:, k].reshape(-1, 1)
            beta = np.linalg.lstsq(fk, X, rcond=None)[0]
            X_pred = fk @ beta
            ve = float(np.sum(X_pred ** 2))
            block_r2[f"Factor{k + 1}"] = ve / total_var if total_var > 0 else 0.0
        variance_explained[block_name] = block_r2

    # Overall proportion per factor (across all blocks)
    overall_r2 = {}
    for k in range(n_factors_actual):
        fk = factor_scores[:, k].reshape(-1, 1)
        cum_ve = 0.0
        for df in blocks_tf.values():
            X = df.values.astype(float)
            X = X - X.mean(axis=0, keepdims=True)
            beta = np.linalg.lstsq(fk, X, rcond=None)[0]
            X_pred = fk @ beta
            cum_ve += float(np.sum(X_pred ** 2))
        overall_r2[f"Factor{k + 1}"] = cum_ve / total_var_all if total_var_all > 0 else 0.0

    # -- 5. Summary plot: all time trends in subplots ---------------------
    n_trends = len(time_trend_plots)
    if n_trends > 0:
        n_cols = min(3, n_trends)
        n_rows = int(np.ceil(n_trends / n_cols))
        fig_summary = make_subplots(
            rows=n_rows,
            cols=n_cols,
            subplot_titles=[p["factor"] for p in time_trend_plots],
            horizontal_spacing=0.12,
            vertical_spacing=0.18,
        )
        for idx, p in enumerate(time_trend_plots):
            row = idx // n_cols + 1
            col = idx % n_cols + 1
            for trace in p["plot"]["data"]:
                fig_summary.add_trace(trace, row=row, col=col)
        fig_summary.update_layout(
            title="MEFISTO Factor Time Trends",
            template="plotly_white",
            height=400 * n_rows,
            width=550 * n_cols,
            showlegend=False,
        )
    else:
        fig_summary = go.Figure().update_layout(
            title="MEFISTO — No valid time trends",
            template="plotly_white",
        )

    return {
        "factors": factors_df.drop(columns=[time_column], errors="ignore"),
        "time_trends": fig_summary.to_dict(),
        "time_trend_individual": time_trend_plots,
        "variance_explained": variance_explained,
        "overall_variance_explained": overall_r2,
        "trend_statistics": trend_stats,
        "engine": "Python::PCA+GAM",
    }


# ─────────────────────────────── Public API

def run_mefisto(
    blocks: Dict[str, pd.DataFrame],
    metadata_df: pd.DataFrame,
    time_column: str,
    subject_column: str,
    n_factors: int = 5,
    smoothness: float = 0.5,
) -> Dict[str, Any]:
    """
    MEFISTO: Spatiotemporal extension of MOFA+ for longitudinal multi-omics.

    Parameters
    ----------
    blocks : dict[str, pd.DataFrame]
        Mapping of omics layer name → sample × feature DataFrame.
        Example: ``{"microbiome": df1, "metabolome": df2}``.
    metadata_df : pd.DataFrame
        Sample metadata indexed by sample ID.  Must contain ``time_column``
        and ``subject_column``.
    time_column : str
        Column name in ``metadata_df`` that holds the continuous time
        covariate (will be coerced to numeric).
    subject_column : str
        Column name in ``metadata_df`` that holds the subject identifier.
    n_factors : int, default 5
        Number of latent factors to infer.
    smoothness : float, default 0.5
        Controls spline flexibility in the Python fallback (0.01 = very
        smooth, 1.0 = very wiggly).  Ignored when the R engine is used.

    Returns
    -------
    dict
        {
            "factors": pd.DataFrame,          # sample × factor scores
            "time_trends": plotly JSON,        # summary subplots
            "time_trend_individual": list,     # per-factor plot dicts
            "variance_explained": dict,        # block → factor → ratio
            "overall_variance_explained": dict,# factor → overall ratio
            "trend_statistics": list,          # per-factor R² / n_knots
            "engine": str,                     # "R::MOFA2" or "Python::PCA+GAM"
        }
    """
    if not blocks:
        raise ValueError("blocks dict must contain at least one omics layer.")
    if metadata_df.empty:
        raise ValueError("metadata_df must be non-empty.")

    logger.info(
        f"MEFISTO start: n_blocks={len(blocks)}, n_factors={n_factors}, "
        f"smoothness={smoothness}"
    )

    # Attempt R engine first
    result = _mefisto_r(
        blocks, metadata_df, time_column, subject_column, n_factors, smoothness
    )
    if result is not None:
        logger.info("MEFISTO completed via R::MOFA2.")
        # Post-process R result to match fallback output shape
        factors_df = result["factors"]
        r2_dict = result.get("r2_dict", {})
        # Build a simple time-trend plot from the R factors
        fig_summary = go.Figure()
        fig_summary.update_layout(
            title="MEFISTO Factors (R engine)",
            template="plotly_white",
            height=400,
            width=600,
        )
        return {
            "factors": factors_df,
            "time_trends": fig_summary.to_dict(),
            "time_trend_individual": [],
            "variance_explained": r2_dict,
            "overall_variance_explained": {},
            "trend_statistics": [],
            "engine": result["engine"],
        }

    # Fallback to pure Python
    logger.info("Falling back to Python PCA+GAM MEFISTO approximation.")
    result = _mefisto_python_fallback(
        blocks, metadata_df, time_column, subject_column, n_factors, smoothness
    )
    logger.info("MEFISTO completed via Python fallback.")
    return result
