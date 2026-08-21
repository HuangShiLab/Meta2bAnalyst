#!/usr/bin/env python3
"""Meta2bAnalyst - ANCOM-BC Differential Abundance Module.

Wraps the ANCOM-BC R package (bias-corrected ANCOM) with support for:
- Multi-group comparisons
- Covariate adjustment
- Random effects (via R ancombc2 when available)
- Volcano plot and sensitivity (cutoff) plot generation

 Falls back to a Python W-statistic approximation when R is unavailable.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app.services.analysis_engine import adjust_pvalues
from app.services.r_analysis import rpackage_available

logger = logging.getLogger(__name__)

# ─────────────────────────────── R availability probe

R_AVAILABLE = False
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr

    R_AVAILABLE = True
    logger.info("rpy2 available in ancom_bc")
except ImportError:
    logger.warning("rpy2 not installed; ANCOM-BC will use Python fallback")


# ─────────────────────────────── Python fallback

def _python_ancombc_fallback(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_var: str,
    covariates: Optional[List[str]] = None,
    p_adj_method: str = "BH",
    pvalue_threshold: float = 0.05,
) -> pd.DataFrame:
    """Python fallback: CLR + per-feature W-stat approximation.

    Ignores covariates (warns if provided). Supports 2 groups only.
    """
    if covariates:
        logger.warning(
            "Python ANCOM-BC fallback does not support covariates; "
            f"ignoring {covariates}"
        )

    # Filter features by zero proportion
    zero_props = (count_df == 0).sum(axis=1) / count_df.shape[1]
    keep_features = zero_props <= 0.9
    count_df = count_df.loc[keep_features]

    if count_df.empty:
        return pd.DataFrame({"error": ["No features remaining after zero filtering"]})

    # CLR transformation
    def _clr(mat: pd.DataFrame) -> pd.DataFrame:
        pseudocount = 0.5
        log_vals = np.log(mat + pseudocount)
        return log_vals.subtract(log_vals.mean(axis=1), axis=0)

    clr_df = _clr(count_df.T).T  # back to features x samples

    groups = metadata_df[group_var].dropna().unique()
    if len(groups) != 2:
        return pd.DataFrame({"error": ["Python fallback requires exactly 2 groups"]})
    g1, g2 = sorted(groups)[0], sorted(groups)[1]
    g1_samples = metadata_df[metadata_df[group_var] == g1].index.intersection(clr_df.columns)
    g2_samples = metadata_df[metadata_df[group_var] == g2].index.intersection(clr_df.columns)

    if len(g1_samples) == 0 or len(g2_samples) == 0:
        return pd.DataFrame({"error": ["One or both groups have no valid samples"]})

    results = []
    for feature in clr_df.index:
        g1_vals = clr_df.loc[feature, g1_samples].dropna().values
        g2_vals = clr_df.loc[feature, g2_samples].dropna().values
        if len(g1_vals) == 0 or len(g2_vals) == 0:
            continue
        lfc = float(g2_vals.mean() - g1_vals.mean())
        se = (
            np.sqrt(
                g1_vals.var(ddof=1) / len(g1_vals)
                + g2_vals.var(ddof=1) / len(g2_vals)
            )
            + 1e-10
        )
        w = lfc / se
        try:
            from scipy.stats import mannwhitneyu
            _, pvalue = mannwhitneyu(g1_vals, g2_vals, alternative="two-sided")
        except Exception:
            pvalue = 1.0
        results.append({
            "feature": feature,
            "lfc": lfc,
            "se": float(se),
            "W": float(w),
            "pvalue": float(pvalue),
        })

    result_df = pd.DataFrame(results)
    if len(result_df) > 0:
        result_df["padj"] = adjust_pvalues(result_df["pvalue"].values, p_adj_method)
        result_df["qvalue"] = result_df["padj"]
        result_df["diff_abn"] = (result_df["padj"] < pvalue_threshold) & (
            result_df["W"].abs() > 2.0
        )
        result_df = result_df.sort_values("pvalue")
    return result_df


# ─────────────────────────────── Plot builders

def _build_volcano_plot(result_df: pd.DataFrame, pvalue_threshold: float) -> go.Figure:
    """Build volcano plot for ANCOM-BC results."""
    df = result_df.copy()
    df["-log10_padj"] = -np.log10(np.maximum(df["padj"], 1e-300))
    df["significant"] = df["diff_abn"] if "diff_abn" in df.columns else df["padj"] < pvalue_threshold

    colours = []
    for _, row in df.iterrows():
        if row["significant"]:
            colours.append("#E15759" if row["lfc"] > 0 else "#4E79A7")
        else:
            colours.append("#BAB0AC")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["lfc"],
            y=df["-log10_padj"],
            mode="markers",
            text=df["feature"],
            marker=dict(size=8, color=colours, opacity=0.8),
            hovertemplate=(
                "<b>%{text}</b><br>LFC: %{x:.3f}<br>-log10(padj): %{y:.3f}<extra></extra>"
            ),
        )
    )
    fig.add_hline(
        y=-np.log10(pvalue_threshold),
        line_dash="dash",
        line_color="grey",
        annotation_text=f"padj = {pvalue_threshold}",
    )
    fig.add_vline(x=0, line_dash="solid", line_color="grey")
    fig.update_layout(
        title="ANCOM-BC Volcano Plot",
        xaxis_title="Log Fold Change (LFC)",
        yaxis_title="-log10(adjusted p-value)",
        template="plotly_white",
        showlegend=False,
    )
    return fig


def _build_sensitivity_plot(result_df: pd.DataFrame) -> go.Figure:
    """Sensitivity plot: number of DA features vs. |W| cutoff."""
    if result_df.empty or "W" not in result_df.columns:
        return go.Figure()

    w_abs = result_df["W"].abs().sort_values(ascending=False).values
    cutoffs = np.linspace(0, max(w_abs) * 1.1, 100)
    n_sig = [(w_abs >= c).sum() for c in cutoffs]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=cutoffs,
            y=n_sig,
            mode="lines",
            line=dict(color="#59A14F", width=2),
            fill="tozeroy",
        )
    )
    fig.update_layout(
        title="ANCOM-BC Sensitivity Analysis",
        xaxis_title="|W| cutoff",
        yaxis_title="Number of differentially abundant features",
        template="plotly_white",
    )
    return fig


# ─────────────────────────────── R driver

def _run_ancombc_r(
    count_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_var: str,
    covariates: Optional[List[str]] = None,
    random_effects: Optional[List[str]] = None,
    pvalue_threshold: float = 0.05,
) -> Optional[pd.DataFrame]:
    """Run ANCOM-BC via rpy2; return DataFrame or None on failure."""
    if not R_AVAILABLE or not rpackage_available("ANCOMBC"):
        return None

    try:
        metadata_copy = metadata_df.copy()
        metadata_copy[group_var] = metadata_copy[group_var].astype(str)
        common_samples = count_df.columns.intersection(metadata_copy.index)
        count_sub = count_df[common_samples]
        meta_sub = metadata_copy.loc[common_samples]

        # Build formula
        fixed_terms = [group_var]
        if covariates:
            for c in covariates:
                if c in meta_sub.columns:
                    fixed_terms.append(c)
                else:
                    logger.warning(f"Covariate '{c}' not in metadata; skipping")
        formula_str = " + ".join(fixed_terms)

        with localconverter(ro.default_converter + pandas2ri.converter):
            r_counts = ro.conversion.py2rpy(count_sub)
            r_meta = ro.conversion.py2rpy(meta_sub)

            # Use ancombc2 if random effects requested, else ancombc
            if random_effects:
                ro.r('''
                run_ancombc2 <- function(counts, coldata, formula_str, group_var,
                                         rand_vars, pvalue_threshold) {
                    library(ANCOMBC)
                    # Filter
                    lib_sizes <- colSums(counts)
                    keep_samples <- lib_sizes >= 0
                    counts <- counts[, keep_samples, drop=FALSE]
                    coldata <- coldata[keep_samples, , drop=FALSE]
                    zero_props <- rowSums(counts == 0) / ncol(counts)
                    keep_features <- zero_props <= 0.9
                    counts <- counts[keep_features, , drop=FALSE]

                    rand_formula <- paste0("(1 | ", rand_vars[1], ")")
                    if (length(rand_vars) > 1) {
                        for (rv in rand_vars[-1]) {
                            rand_formula <- paste0(rand_formula, " + (1 | ", rv, ")")
                        }
                    }
                    full_formula <- paste0(formula_str, " + ", rand_formula)

                    out <- ancombc2(
                        data = counts,
                        tax_data = NULL,
                        formula = full_formula,
                        group = group_var,
                        p_adj_method = "BH",
                        struc_zero = TRUE,
                        neg_lb = TRUE
                    )
                    res <- out$res
                    res_df <- as.data.frame(res)
                    res_df$feature <- rownames(res_df)
                    rownames(res_df) <- NULL
                    return(res_df)
                }
                ''')
                r_func = ro.r["run_ancombc2"]
                result_r = r_func(
                    r_counts,
                    r_meta,
                    formula_str,
                    group_var,
                    ro.StrVector(random_effects),
                    pvalue_threshold,
                )
            else:
                ro.r('''
                run_ancombc <- function(counts, coldata, formula_str, group_var,
                                        pvalue_threshold) {
                    library(ANCOMBC)
                    lib_sizes <- colSums(counts)
                    keep_samples <- lib_sizes >= 0
                    counts <- counts[, keep_samples, drop=FALSE]
                    coldata <- coldata[keep_samples, , drop=FALSE]
                    zero_props <- rowSums(counts == 0) / ncol(counts)
                    keep_features <- zero_props <= 0.9
                    counts <- counts[keep_features, , drop=FALSE]

                    out <- ancombc(
                        data = counts,
                        tax_data = NULL,
                        formula = paste0("~ ", formula_str),
                        group = group_var,
                        p_adj_method = "BH",
                        struc_zero = TRUE,
                        neg_lb = TRUE
                    )
                    res <- out$res
                    res_df <- as.data.frame(res)
                    res_df$feature <- rownames(res_df)
                    rownames(res_df) <- NULL
                    return(res_df)
                }
                ''')
                r_func = ro.r["run_ancombc"]
                result_r = r_func(r_counts, r_meta, formula_str, group_var, pvalue_threshold)

            result_df = ro.conversion.rpy2py(result_r)

        # Normalise column names across ancombc / ancombc2
        result_df = result_df.dropna(subset=["feature"])
        result_df = result_df.sort_values(
            [c for c in result_df.columns if "p_adj" in c or "padj" in c][0]
            if any("p_adj" in c or "padj" in c for c in result_df.columns)
            else result_df.columns[0]
        )

        # Create canonical columns if missing
        if "lfc" not in result_df.columns:
            lfc_candidates = [c for c in result_df.columns if "diff" in c.lower() or "lfc" in c.lower()]
            if lfc_candidates:
                result_df["lfc"] = result_df[lfc_candidates[0]]
            else:
                result_df["lfc"] = 0.0
        if "padj" not in result_df.columns:
            padj_candidates = [c for c in result_df.columns if "p_adj" in c or "padj" in c or "FDR" in c]
            if padj_candidates:
                result_df["padj"] = result_df[padj_candidates[0]]
            else:
                result_df["padj"] = 1.0
        if "W" not in result_df.columns:
            w_candidates = [c for c in result_df.columns if "W" in c or "stat" in c.lower()]
            if w_candidates:
                result_df["W"] = result_df[w_candidates[0]]
            else:
                result_df["W"] = 0.0
        if "pvalue" not in result_df.columns:
            result_df["pvalue"] = result_df["padj"]
        if "diff_abn" not in result_df.columns:
            result_df["diff_abn"] = result_df["padj"] < pvalue_threshold

        return result_df

    except Exception as e:
        logger.error(f"ANCOM-BC R analysis failed: {e}")
        return None


# ─────────────────────────────── Public API

def run_ancom_bc(
    df,
    metadata_df,
    group_column,
    covariates=None,
    random_effects=None,
    pvalue_threshold=0.05,
):
    """Run ANCOM-BC differential abundance analysis.

    Parameters
    ----------
    df : pd.DataFrame
        Raw count matrix (features x samples).
    metadata_df : pd.DataFrame
        Sample metadata indexed by sample ID.
    group_column : str
        Grouping variable.
    covariates : list[str] | None
        Additional fixed-effect covariates.
    random_effects : list[str] | None
        Random-effect columns (requires ancombc2 in R).
    pvalue_threshold : float
        Significance threshold for adjusted p-values.

    Returns
    -------
    dict
        {
            "significant_features": pd.DataFrame,
            "volcano_plot": plotly.graph_objects.Figure,
            "sensitivity_plot": plotly.graph_objects.Figure,
        }
    """
    covariates = covariates or []
    random_effects = random_effects or []

    result_df = _run_ancombc_r(
        df, metadata_df, group_column, covariates, random_effects, pvalue_threshold
    )

    engine = "R::ANCOMBC"
    if result_df is None:
        logger.warning("ANCOMBC not available via rpy2, using Python fallback")
        result_df = _python_ancombc_fallback(
            df, metadata_df, group_column, covariates, "BH", pvalue_threshold
        )
        engine = "python-approx::ancombc"

    if "error" in result_df.columns:
        return {
            "significant_features": result_df,
            "volcano_plot": go.Figure(),
            "sensitivity_plot": go.Figure(),
            "error": result_df["error"].tolist(),
        }

    sig_df = result_df[result_df["diff_abn"]].copy() if "diff_abn" in result_df.columns else pd.DataFrame()

    return {
        "significant_features": sig_df,
        "volcano_plot": _build_volcano_plot(result_df, pvalue_threshold),
        "sensitivity_plot": _build_sensitivity_plot(result_df),
        "statistics": {
            "engine": engine,
            "n_features_tested": int(len(result_df)),
            "n_significant": int(sig_df.shape[0]),
            "n_up": int((sig_df["lfc"] > 0).sum()) if not sig_df.empty else 0,
            "n_down": int((sig_df["lfc"] < 0).sum()) if not sig_df.empty else 0,
            "pvalue_threshold": pvalue_threshold,
            "covariates": covariates,
            "random_effects": random_effects,
        },
    }
