#!/usr/bin/env python3
"""Meta2bAnalyst - Stratified PERMANOVA Module.

Wraps vegan::adonis2 via rpy2 to support:
- Stratified (blocked) permutations  (strata_column)
- Covariate adjustment
- Multiple distance metrics
- PCoA visualisation

 Falls back to skbio.stats.distance.permanova (no strata support) when R
 is unavailable.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.spatial.distance import pdist, squareform

from app.services.analysis_engine import AnalysisEngine

logger = logging.getLogger(__name__)

# ─────────────────────────────── R availability probe

R_AVAILABLE = False
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr

    R_AVAILABLE = True
    logger.info("rpy2 available in permanova_strata")
except ImportError:
    logger.warning("rpy2 not installed; PERMANOVA will fall back to skbio")


def _distance_matrix(
    df: pd.DataFrame, metric: str = "braycurtis"
) -> pd.DataFrame:
    """Compute sample x sample distance matrix from feature table (features x samples)."""
    X = df.T.fillna(0).astype(float).values

    if metric == "braycurtis":
        def _bray(x, y):
            return np.sum(np.abs(x - y)) / np.sum(x + y) if np.sum(x + y) > 0 else 0.0
        dist = squareform(pdist(X, _bray))
    elif metric == "jaccard":
        def _jaccard(x, y):
            xb = x > 0
            yb = y > 0
            union = np.sum(xb | yb)
            inter = np.sum(xb & yb)
            return 1 - inter / union if union > 0 else 0.0
        dist = squareform(pdist(X, _jaccard))
    elif metric == "euclidean":
        dist = squareform(pdist(X, metric="euclidean"))
    elif metric == "manhattan":
        dist = squareform(pdist(X, metric="cityblock"))
    elif metric == "canberra":
        dist = squareform(pdist(X, metric="canberra"))
    elif metric == "aitchison":
        # CLR then Euclidean
        pseudocount = 0.5
        log_vals = np.log(df.T.fillna(0) + pseudocount)
        clr = log_vals.subtract(log_vals.mean(axis=1), axis=0)
        dist = squareform(pdist(clr.values, metric="euclidean"))
    else:
        dist = squareform(pdist(X, metric="euclidean"))

    return pd.DataFrame(dist, index=df.columns, columns=df.columns)


def _run_permanova_r(
    dist_matrix: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    strata_column: Optional[str] = None,
    covariates: Optional[List[str]] = None,
    n_permutations: int = 999,
) -> Optional[Dict[str, Any]]:
    """Run vegan::adonis2 via rpy2."""
    if not R_AVAILABLE:
        return None
    try:
        importr("vegan")
    except Exception as e:
        logger.warning(f"vegan R package not available: {e}")
        return None

    samples = dist_matrix.index.intersection(metadata_df.index)
    if len(samples) == 0:
        raise ValueError("No overlap between distance matrix and metadata")

    dist_sub = dist_matrix.loc[samples, samples]
    meta_sub = metadata_df.loc[samples].copy()
    meta_sub[group_column] = meta_sub[group_column].astype(str)
    if strata_column and strata_column in meta_sub.columns:
        meta_sub[strata_column] = meta_sub[strata_column].astype(str)

    # Build formula
    terms = [group_column]
    if covariates:
        for c in covariates:
            if c in meta_sub.columns:
                terms.append(c)
            else:
                logger.warning(f"Covariate '{c}' missing from metadata; skipping")
    formula_rhs = " + ".join(terms)

    with localconverter(ro.default_converter + pandas2ri.converter):
        r_dist = ro.conversion.py2rpy(dist_sub)
        r_meta = ro.conversion.py2rpy(meta_sub)

        if strata_column and strata_column in meta_sub.columns:
            ro.r('''
            run_adonis2_strata <- function(dist_mat, meta, formula_str,
                                           group_var, strata_var, n_perm) {
                library(vegan)
                # adonis2 requires a formula with data frame
                meta[[group_var]] <- factor(meta[[group_var]])
                meta[[strata_var]] <- factor(meta[[strata_var]])
                f <- as.formula(paste0("dist_mat ~ ", formula_str))
                res <- adonis2(f, data = meta, permutations = n_perm,
                               strata = meta[[strata_var]], by = "margin")
                # Convert to data frame for easy extraction
                res_df <- as.data.frame(res)
                res_df$term <- rownames(res_df)
                rownames(res_df) <- NULL
                return(list(aov_table = res_df, call = "adonis2_with_strata"))
            }
            ''')
            r_func = ro.r["run_adonis2_strata"]
            result_r = r_func(
                r_dist, r_meta, formula_rhs, group_column, strata_column, n_permutations
            )
        else:
            ro.r('''
            run_adonis2 <- function(dist_mat, meta, formula_str,
                                    group_var, n_perm) {
                library(vegan)
                meta[[group_var]] <- factor(meta[[group_var]])
                f <- as.formula(paste0("dist_mat ~ ", formula_str))
                res <- adonis2(f, data = meta, permutations = n_perm, by = "margin")
                res_df <- as.data.frame(res)
                res_df$term <- rownames(res_df)
                rownames(res_df) <- NULL
                return(list(aov_table = res_df, call = "adonis2"))
            }
            ''')
            r_func = ro.r["run_adonis2"]
            result_r = r_func(r_dist, r_meta, formula_rhs, group_column, n_permutations)

        aov_table = ro.conversion.rpy2py(result_r.rx2("aov_table"))

    # Extract key statistics
    group_row = aov_table[aov_table["term"] == group_column]
    if group_row.empty:
        # Try first non-Residual row
        group_row = aov_table[
            (aov_table["term"] != "Residual") & (~aov_table["term"].isna())
        ].head(1)

    if not group_row.empty:
        r2 = float(group_row.iloc[0].get("R2", np.nan))
        f_stat = float(group_row.iloc[0].get("F", np.nan))
        pvalue = float(group_row.iloc[0].get("Pr(>F)", np.nan))
        df_num = int(group_row.iloc[0].get("Df", 0)) if not pd.isna(group_row.iloc[0].get("Df")) else 0
    else:
        r2 = f_stat = pvalue = np.nan
        df_num = 0

    n_samples = len(samples)
    residual_df = aov_table[aov_table["term"] == "Residual"]
    df_den = int(residual_df["Df"].iloc[0]) if not residual_df.empty else (n_samples - 1)

    # Significant variables: all terms with Pr(>F) < 0.05
    sig_vars = []
    if "Pr(>F)" in aov_table.columns:
        sig_rows = aov_table[
            (aov_table["Pr(>F)"] < 0.05)
            & (aov_table["term"] != "Residual")
            & (~aov_table["term"].isna())
        ]
        sig_vars = sig_rows["term"].tolist()

    return {
        "pseudo_f": float(f_stat) if not pd.isna(f_stat) else None,
        "r_squared": float(r2) if not pd.isna(r2) else None,
        "pvalue": float(pvalue) if not pd.isna(pvalue) else None,
        "df_between": int(df_num),
        "df_within": int(df_den),
        "n_permutations": n_permutations,
        "n_samples": int(n_samples),
        "strata_column": strata_column,
        "significant": bool(pvalue < 0.05) if not pd.isna(pvalue) else False,
        "significant_variables": sig_vars,
        "aov_table": aov_table.to_dict(orient="records"),
        "engine": "R::vegan::adonis2",
    }


def _run_permanova_skbio(
    dist_matrix: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    n_permutations: int = 999,
) -> Optional[Dict[str, Any]]:
    """Fallback using scikit-bio (no strata support)."""
    try:
        from skbio.stats.distance import permanova
    except ImportError:
        logger.warning("skbio not installed; cannot run PERMANOVA fallback")
        return None

    samples = dist_matrix.index.intersection(metadata_df.index)
    dist_sub = dist_matrix.loc[samples, samples]
    meta_sub = metadata_df.loc[samples]

    # skbio expects DistanceMatrix object
    from skbio import DistanceMatrix
    dm = DistanceMatrix(dist_sub.values, ids=list(dist_sub.index))
    grouping = meta_sub[group_column].loc[list(dm.ids)]

    result = permanova(dm, grouping, permutations=n_permutations)

    return {
        "pseudo_f": float(result["test statistic"]),
        "r_squared": None,  # skbio permanova does not return R2 directly
        "pvalue": float(result["p-value"]),
        "df_between": int(result["number of groups"] - 1),
        "df_within": int(len(samples) - result["number of groups"]),
        "n_permutations": n_permutations,
        "n_samples": int(len(samples)),
        "strata_column": None,
        "significant": bool(result["p-value"] < 0.05),
        "significant_variables": [group_column] if result["p-value"] < 0.05 else [],
        "aov_table": [],
        "engine": "python::skbio.permanova",
    }


def _build_pcoa_plot(
    dist_matrix: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    strata_column: Optional[str] = None,
) -> go.Figure:
    """Generate PCoA scatter coloured by group, shaped by strata (if provided)."""
    engine = AnalysisEngine()
    pcoa_result = engine.pcoa(dist_matrix)
    coords = pcoa_result["samples"]

    samples = coords.index.intersection(metadata_df.index)
    coords = coords.loc[samples]
    meta = metadata_df.loc[samples]

    groups = meta[group_column].astype(str)
    unique_groups = sorted(groups.unique())
    palette = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
               "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC"]
    group_colours = {g: palette[i % len(palette)] for i, g in enumerate(unique_groups)}

    fig = go.Figure()
    for g in unique_groups:
        mask = groups == g
        symbol = "circle"
        if strata_column and strata_column in meta.columns:
            # Add traces per stratum to allow shape encoding
            strata = meta.loc[mask, strata_column].astype(str)
            unique_strata = sorted(strata.unique())
            symbols = ["circle", "square", "diamond", "cross", "x", "star"]
            for i, s in enumerate(unique_strata):
                s_mask = mask & (meta[strata_column].astype(str) == s)
                fig.add_trace(
                    go.Scatter(
                        x=coords.loc[s_mask, "PC1"],
                        y=coords.loc[s_mask, "PC2"],
                        mode="markers",
                        name=f"{g} ({s})",
                        marker=dict(
                            size=10,
                            color=group_colours[g],
                            symbol=symbols[i % len(symbols)],
                            line=dict(width=1, color="DarkSlateGrey"),
                        ),
                        hovertemplate=(
                            f"<b>%{{text}}</b><br>Group: {g}<br>Stratum: {s}<br>"
                            "PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>"
                        ),
                        text=coords.loc[s_mask].index,
                    )
                )
        else:
            fig.add_trace(
                go.Scatter(
                    x=coords.loc[mask, "PC1"],
                    y=coords.loc[mask, "PC2"],
                    mode="markers",
                    name=str(g),
                    marker=dict(
                        size=10,
                        color=group_colours[g],
                        line=dict(width=1, color="DarkSlateGrey"),
                    ),
                    hovertemplate=(
                        f"<b>%{{text}}</b><br>Group: {g}<br>"
                        "PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>"
                    ),
                    text=coords.loc[mask].index,
                )
            )

    ve = pcoa_result.get("variance_explained", [0, 0])
    pc1_ve = ve[0] if len(ve) > 0 else 0
    pc2_ve = ve[1] if len(ve) > 1 else 0

    fig.update_layout(
        title="PCoA (PERMANOVA)",
        xaxis_title=f"PC1 ({pc1_ve:.1f}%)",
        yaxis_title=f"PC2 ({pc2_ve:.1f}%)",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=-0.3),
    )
    return fig


# ─────────────────────────────── Public API

def run_permanova_strata(
    df,
    metadata_df,
    group_column,
    strata_column=None,
    covariates=None,
    distance_metric="braycurtis",
    n_permutations=999,
):
    """Stratified PERMANOVA with PCoA visualisation.

    Parameters
    ----------
    df : pd.DataFrame
        Feature table (features x samples).
    metadata_df : pd.DataFrame
        Sample metadata indexed by sample ID.
    group_column : str
        Primary grouping variable.
    strata_column : str | None
        Blocking variable for restricted permutations.
    covariates : list[str] | None
        Additional covariates for the model.
    distance_metric : str
        "braycurtis", "jaccard", "euclidean", "manhattan", "canberra", "aitchison".
    n_permutations : int
        Number of permutations for the test.

    Returns
    -------
    dict
        {
            "statistics": dict,
            "significant_variables": list[str],
            "plot_data": plotly.graph_objects.Figure,
        }
    """
    covariates = covariates or []

    # 1. Distance matrix
    dist_matrix = _distance_matrix(df, distance_metric)

    # 2. Try R first
    result = _run_permanova_r(
        dist_matrix,
        metadata_df,
        group_column,
        strata_column,
        covariates,
        n_permutations,
    )

    if result is None:
        logger.warning("R vegan::adonis2 unavailable; falling back to skbio.permanova")
        if strata_column:
            logger.warning("Python fallback does NOT support strata; running unstratified PERMANOVA")
        result = _run_permanova_skbio(
            dist_matrix, metadata_df, group_column, n_permutations
        )

    if result is None:
        raise RuntimeError(
            "PERMANOVA could not be executed: neither R vegan nor skbio is available."
        )

    # 3. PCoA plot
    plot_fig = _build_pcoa_plot(dist_matrix, metadata_df, group_column, strata_column)

    return {
        "statistics": result,
        "significant_variables": result.get("significant_variables", []),
        "plot_data": plot_fig,
    }
