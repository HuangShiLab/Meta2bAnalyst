#!/usr/bin/env python3
"""Meta2bAnalyst — Missing-value Imputation
Supports KNN, random forest, QRILC, half-min and min imputation with
R integration via rpy2 and Python fallbacks.
"""
import logging
from typing import Any, Dict, Optional

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
    logger.info("rpy2 available for imputation")

    for pkg in ['missForest', 'imputeLCMD', 'sva']:
        try:
            importr(pkg)
            R_PACKAGES[pkg] = True
            logger.info(f"R package {pkg} available")
        except Exception as e:
            R_PACKAGES[pkg] = False
            logger.warning(f"R package {pkg} not available: {e}")
except ImportError as e:
    logger.warning(f"rpy2 not installed ({e}). Imputation will use Python fallbacks.")


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


# ── Python imputation helpers ─────────────────────────────────────────────

def _impute_half_min(df: pd.DataFrame) -> pd.DataFrame:
    """Replace each missing value with half the minimum non-zero value of its feature."""
    result = df.copy().astype(float)
    for feature in result.index:
        vals = result.loc[feature]
        non_zero = vals[vals > 0].dropna()
        if len(non_zero) > 0:
            half_min = non_zero.min() / 2.0
        else:
            half_min = 1e-6
        result.loc[feature] = vals.fillna(half_min)
    return result


def _impute_min(df: pd.DataFrame) -> pd.DataFrame:
    """Replace each missing value with the minimum non-zero value of its feature."""
    result = df.copy().astype(float)
    for feature in result.index:
        vals = result.loc[feature]
        non_zero = vals[vals > 0].dropna()
        if len(non_zero) > 0:
            min_val = non_zero.min()
        else:
            min_val = 1e-6
        result.loc[feature] = vals.fillna(min_val)
    return result


def _impute_knn(df: pd.DataFrame, n_neighbors: int = 5) -> pd.DataFrame:
    """KNN imputation via sklearn (samples in columns)."""
    from sklearn.impute import KNNImputer

    # KNNImputer works on samples (rows); we need features (rows) -> transpose
    X = df.T.values
    imputer = KNNImputer(n_neighbors=n_neighbors, weights="distance")
    X_imp = imputer.fit_transform(X)
    result = pd.DataFrame(X_imp, index=df.columns, columns=df.index).T
    result.index = df.index
    result.columns = df.columns
    return result


def _impute_rf_sklearn(df: pd.DataFrame, max_iter: int = 10) -> pd.DataFrame:
    """Random-forest imputation via sklearn IterativeImputer (Python fallback)."""
    from sklearn.experimental import enable_iterative_imputer  # noqa: F401
    from sklearn.impute import IterativeImputer
    from sklearn.ensemble import ExtraTreesRegressor

    X = df.T.values
    estimator = ExtraTreesRegressor(
        n_estimators=50,
        max_depth=10,
        random_state=42,
        n_jobs=-1,
    )
    imputer = IterativeImputer(
        estimator=estimator,
        max_iter=max_iter,
        random_state=42,
        sample_posterior=True,
    )
    X_imp = imputer.fit_transform(X)
    result = pd.DataFrame(X_imp, index=df.columns, columns=df.index).T
    result.index = df.index
    result.columns = df.columns
    return result


# ── R wrappers ────────────────────────────────────────────────────────────

def _impute_rf_r(df: pd.DataFrame, maxiter: int = 10, ntree: int = 100) -> pd.DataFrame:
    """missForest imputation via rpy2."""
    with localconverter(ro.default_converter + pandas2ri.converter):
        r_data = ro.conversion.py2rpy(df.astype(float))
        ro.r('''
        run_missforest <- function(dat, maxiter, ntree) {
            library(missForest)
            imp <- missForest(as.matrix(dat), maxiter=maxiter, ntree=ntree)
            return(as.data.frame(imp$ximp))
        }
        ''')
        r_func = ro.r['run_missforest']
        result_r = r_func(r_data, maxiter, ntree)
        result_df = ro.conversion.rpy2py(result_r)
    result_df.index = df.index
    result_df.columns = df.columns
    return result_df


def _impute_qrilc_r(df: pd.DataFrame, tune_sigma: float = 1.0) -> pd.DataFrame:
    """QRILC imputation via rpy2 (imputeLCMD package).

    QRILC assumes left-censored missingness (common in metabolomics / proteomics).
    Data is log-transformed internally by the R function.
    """
    with localconverter(ro.default_converter + pandas2ri.converter):
        r_data = ro.conversion.py2rpy(df.astype(float))
        ro.r('''
        run_qrilc <- function(dat, tune_sigma) {
            library(imputeLCMD)
            # QRILC expects samples as rows, features as columns
            imp <- impute.QRILC(t(dat), tune.sigma=tune_sigma)
            # imp is a list; the imputed matrix is imp[[1]]
            imp_mat <- as.data.frame(t(imp[[1]]))
            return(imp_mat)
        }
        ''')
        r_func = ro.r['run_qrilc']
        result_r = r_func(r_data, tune_sigma)
        result_df = ro.conversion.rpy2py(result_r)
    result_df.index = df.index
    result_df.columns = df.columns
    return result_df


# ── Visualisation helpers ─────────────────────────────────────────────────

def _make_missingness_heatmap(
    before_df: pd.DataFrame,
    after_df: pd.DataFrame,
) -> Dict[str, Any]:
    """Return side-by-side heatmaps of missing-value patterns before/after."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        logger.warning("plotly not available; skipping missingness heatmap")
        return {}

    # Downsample for visualisation if matrix is huge
    max_features = 200
    max_samples = 200

    before_vis = before_df.copy()
    after_vis = after_df.copy()
    if before_vis.shape[0] > max_features:
        before_vis = before_vis.sample(max_features, random_state=42)
        after_vis = after_vis.loc[before_vis.index]
    if before_vis.shape[1] > max_samples:
        cols = before_vis.columns.to_series().sample(max_samples, random_state=42).sort_index()
        before_vis = before_vis[cols]
        after_vis = after_vis[cols]

    # Binary missing matrix
    missing_before = before_vis.isna().astype(int).values
    missing_after = after_vis.isna().astype(int).values

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Before imputation", "After imputation"),
        horizontal_spacing=0.08,
    )

    fig.add_trace(
        go.Heatmap(
            z=missing_before,
            x=list(before_vis.columns),
            y=list(before_vis.index),
            colorscale=[[0, "#F7F7F7"], [1, "#E15759"]],
            showscale=False,
            name="Missing",
            hovertemplate="Sample: %{x}<br>Feature: %{y}<br>Missing: %{z}<extra></extra>",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Heatmap(
            z=missing_after,
            x=list(after_vis.columns),
            y=list(after_vis.index),
            colorscale=[[0, "#F7F7F7"], [1, "#59A14F"]],
            showscale=False,
            name="Missing",
            hovertemplate="Sample: %{x}<br>Feature: %{y}<br>Missing: %{z}<extra></extra>",
        ),
        row=1, col=2,
    )

    fig.update_layout(
        title_text="Missing value pattern (1 = missing)",
        template="plotly_white",
        height=max(400, min(800, before_vis.shape[0] * 12)),
        width=950,
    )
    fig.update_xaxes(tickangle=45)

    return fig.to_dict()


def _make_imputation_summary(
    before_df: pd.DataFrame,
    after_df: pd.DataFrame,
    method: str,
    engine: str,
    dropped_features: list,
) -> Dict[str, Any]:
    """Build a structured summary dict."""
    n_total = before_df.shape[0]
    n_samples = before_df.shape[1]
    missing_before = int(before_df.isna().sum().sum())
    missing_after = int(after_df.isna().sum().sum())
    pct_missing_before = round(100 * missing_before / (n_total * n_samples), 2)
    pct_missing_after = round(100 * missing_after / (n_total * n_samples), 2)

    # Per-feature missingness stats
    feature_missing_pct = (before_df.isna().sum(axis=1) / n_samples * 100).round(2)

    return {
        "method": method,
        "engine": engine,
        "n_features_total": n_total,
        "n_features_retained": after_df.shape[0],
        "n_features_dropped": len(dropped_features),
        "dropped_features": dropped_features,
        "n_samples": n_samples,
        "missing_values_before": missing_before,
        "missing_values_after": missing_after,
        "pct_missing_before": pct_missing_before,
        "pct_missing_after": pct_missing_after,
        "max_feature_missing_pct": float(feature_missing_pct.max()),
        "mean_feature_missing_pct": float(feature_missing_pct.mean()),
    }


# ── Public API ────────────────────────────────────────────────────────────

def run_imputation(
    df: pd.DataFrame,
    method: str = "knn",
    missing_threshold: float = 0.5,
    data_type: str = "microbiome",
) -> Dict[str, Any]:
    """Run missing-value imputation and return imputed matrix + summary + plot.

    Parameters
    ----------
    df : pd.DataFrame
        Feature × sample matrix.
    method : {"knn", "rf", "qrilc", "half_min", "min"}
        Imputation algorithm.
    missing_threshold : float
        Features with missing proportion > threshold are removed before
        imputation (default 0.5 = 50 %%).
    data_type : str
        Hint for logging (e.g. "microbiome", "metabolome").

    Returns
    -------
    dict
        {
            "imputed_matrix": pd.DataFrame,
            "imputation_summary": dict,
            "plot_data": dict,   # Plotly JSON
        }
    """
    if df.empty:
        raise ValueError("Input data frame is empty")

    # ── Step 1: Filter features by missing-rate threshold ──
    missing_rates = df.isna().sum(axis=1) / df.shape[1]
    keep = missing_rates <= missing_threshold
    dropped_features = df.index[~keep].tolist()
    df_filtered = df.loc[keep].copy()

    if df_filtered.empty:
        raise ValueError(
            f"All features removed after missing-rate filtering (threshold={missing_threshold}). "
            "Consider raising missing_threshold."
        )

    logger.info(
        f"Imputation: {df.shape[0]} features, {df.shape[1]} samples; "
        f"retained {df_filtered.shape[0]} features (threshold={missing_threshold})"
    )

    # ── Step 2: Route to engine ──
    engine = "python"
    imputed: Optional[pd.DataFrame] = None

    if method == "knn":
        imputed = _impute_knn(df_filtered, n_neighbors=5)
        engine = "python::sklearn.KNNImputer"

    elif method == "rf":
        if R_AVAILABLE and _rpackage_available('missForest'):
            try:
                imputed = _impute_rf_r(df_filtered)
                engine = "R::missForest"
            except Exception as e:
                logger.error(f"missForest R failed: {e}; falling back to sklearn IterativeImputer")
                imputed = _impute_rf_sklearn(df_filtered)
                engine = "python::sklearn.IterativeImputer"
        else:
            imputed = _impute_rf_sklearn(df_filtered)
            engine = "python::sklearn.IterativeImputer"

    elif method == "qrilc":
        if R_AVAILABLE and _rpackage_available('imputeLCMD'):
            try:
                imputed = _impute_qrilc_r(df_filtered)
                engine = "R::imputeLCMD::impute.QRILC"
            except Exception as e:
                logger.error(f"QRILC R failed: {e}; falling back to half-min")
                imputed = _impute_half_min(df_filtered)
                engine = "python::half_min"
        else:
            imputed = _impute_half_min(df_filtered)
            engine = "python::half_min"

    elif method == "half_min":
        imputed = _impute_half_min(df_filtered)
        engine = "python::half_min"

    elif method == "min":
        imputed = _impute_min(df_filtered)
        engine = "python::min"

    else:
        raise ValueError(f"Unknown imputation method: {method}")

    # ── Step 3: Build outputs ──
    summary = _make_imputation_summary(
        before_df=df,
        after_df=imputed,
        method=method,
        engine=engine,
        dropped_features=dropped_features,
    )

    heatmap = _make_missingness_heatmap(df, imputed)
    plot_data = {"missingness_heatmap": heatmap} if heatmap else {}

    return {
        "imputed_matrix": imputed,
        "imputation_summary": summary,
        "plot_data": plot_data,
    }
