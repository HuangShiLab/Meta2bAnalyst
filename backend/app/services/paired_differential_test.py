#!/usr/bin/env python3
"""Meta2bAnalyst - Paired Differential Test Module.

Implements paired differential abundance testing for repeated-measures
microbiome designs (e.g. pre/post, case/control matched by subject).

Methods
-------
paired_wilcoxon : CLR transform + scipy.stats.wilcoxon (paired signed-rank).
paired_aldex2   : rpy2 + ALDEx2 with Monte-Carlo Dirichlet sampling;
                  falls back to paired_wilcoxon when R is unavailable.

All methods apply Benjamini-Hochberg FDR correction and emit an
interactive Plotly volcano plot.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy import stats

from app.services.analysis_engine import adjust_pvalues

logger = logging.getLogger(__name__)

# ─────────────────────────────── R availability probe (mirrors r_analysis.py)

R_AVAILABLE = False
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr

    R_AVAILABLE = True
    logger.info("rpy2 available in paired_differential_test")
except ImportError:
    logger.warning("rpy2 not installed; paired_aldex2 will fall back to paired_wilcoxon")


def _clr_transform(df: pd.DataFrame, pseudocount: float = 0.5) -> pd.DataFrame:
    """Centered Log-Ratio transformation (samples x features -> same)."""
    df_pseudo = df + pseudocount
    log_vals = np.log(df_pseudo)
    row_means = log_vals.mean(axis=1)
    return log_vals.subtract(row_means, axis=0)


def _build_volcano_plot(
    result_df: pd.DataFrame,
    effect_col: str,
    pval_col: str,
    padj_col: str,
    pvalue_threshold: float,
    title: str = "Paired Differential Volcano Plot",
) -> go.Figure:
    """Build an interactive Plotly volcano plot."""
    df = result_df.copy()
    df["-log10_padj"] = -np.log10(np.maximum(df[padj_col], 1e-300))
    df["significant"] = (df[padj_col] < pvalue_threshold) & (df[effect_col].abs() > 0.5)

    # Colour mapping
    colours = []
    for _, row in df.iterrows():
        if row["significant"]:
            colours.append("#E15759" if row[effect_col] > 0 else "#4E79A7")
        else:
            colours.append("#BAB0AC")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df[effect_col],
            y=df["-log10_padj"],
            mode="markers",
            text=df["feature"],
            marker=dict(size=8, color=colours, opacity=0.8),
            hovertemplate=(
                "<b>%{text}</b><br>"
                + f"{effect_col}: %{{x:.3f}}<br>"
                + "-log10(padj): %{y:.3f}<extra></extra>"
            ),
        )
    )

    # Threshold lines
    fig.add_hline(
        y=-np.log10(pvalue_threshold),
        line_dash="dash",
        line_color="grey",
        annotation_text=f"padj = {pvalue_threshold}",
    )
    fig.add_vline(x=0, line_dash="solid", line_color="grey")
    fig.add_vline(x=0.5, line_dash="dash", line_color="grey")
    fig.add_vline(x=-0.5, line_dash="dash", line_color="grey")

    fig.update_layout(
        title=title,
        xaxis_title=effect_col,
        yaxis_title="-log10(adjusted p-value)",
        template="plotly_white",
        showlegend=False,
    )
    return fig


def _validate_paired_structure(
    metadata_df: pd.DataFrame, subject_column: str, group_column: str
) -> None:
    """Ensure every subject has exactly 2 samples and both groups are present."""
    if subject_column not in metadata_df.columns:
        raise ValueError(f"subject_column '{subject_column}' not found in metadata")
    if group_column not in metadata_df.columns:
        raise ValueError(f"group_column '{group_column}' not found in metadata")

    subject_counts = metadata_df[subject_column].value_counts()
    bad_subjects = subject_counts[subject_counts != 2]
    if not bad_subjects.empty:
        raise ValueError(
            f"Paired test requires exactly 2 samples per subject. "
            f"Offending subjects: {bad_subjects.to_dict()}"
        )

    groups = metadata_df[group_column].dropna().unique()
    if len(groups) != 2:
        raise ValueError(
            f"Paired test requires exactly 2 groups, found {len(groups)}: {list(groups)}"
        )


def _pivot_paired(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    subject_column: str,
    group_column: str,
) -> tuple[pd.DataFrame, str, str]:
    """Pivot paired data so each row = subject, columns = feature_x_group.

    Returns
    -------
    pivoted : DataFrame  (subjects x 2*features)
    g1, g2  : group labels (sorted for stability)
    """
    common = df.columns.intersection(metadata_df.index)
    df = df[common]
    meta = metadata_df.loc[common]

    groups = sorted(meta[group_column].dropna().unique())
    g1, g2 = groups[0], groups[1]

    # Attach group info to columns temporarily
    col_df = pd.DataFrame({
        "sample": df.columns,
        "subject": meta[subject_column].values,
        "group": meta[group_column].values,
    })

    # Long format
    long = df.T.reset_index().melt(id_vars="index")
    long = long.rename(columns={"index": "sample", "variable": "feature", "value": "abundance"})
    long = long.merge(col_df, on="sample")

    # Pivot to wide: subject x (feature_group)
    wide = long.pivot_table(
        index="subject",
        columns=["feature", "group"],
        values="abundance",
        aggfunc="first",
    )
    # Flatten multi-index columns
    wide.columns = [f"{feat}_{grp}" for feat, grp in wide.columns]
    return wide, g1, g2


def _run_paired_wilcoxon(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    subject_column: str,
    transformation: str = "clr",
    pvalue_threshold: float = 0.05,
) -> Dict[str, Any]:
    """Python paired Wilcoxon signed-rank test per feature."""
    _validate_paired_structure(metadata_df, subject_column, group_column)

    common = df.columns.intersection(metadata_df.index)
    df = df[common]
    meta = metadata_df.loc[common]

    # Transpose to samples x features for CLR
    X = df.T

    if transformation.lower() == "clr":
        X_trans = _clr_transform(X)
    elif transformation.lower() == "log":
        X_trans = np.log1p(X)
    elif transformation.lower() == "none":
        X_trans = X
    else:
        raise ValueError(f"Unknown transformation: {transformation}")

    wide, g1, g2 = _pivot_paired(X_trans, meta, subject_column, group_column)

    results = []
    features = sorted({c.rsplit(f"_{g2}", 1)[0] for c in wide.columns if c.endswith(f"_{g2}")})
    for feat in features:
        col1 = f"{feat}_{g1}"
        col2 = f"{feat}_{g2}"
        if col1 not in wide.columns or col2 not in wide.columns:
            continue
        pair = wide[[col1, col2]].dropna()
        if len(pair) < 3:
            continue
        try:
            stat, pvalue = stats.wilcoxon(pair[col1], pair[col2], alternative="two-sided")
        except Exception as e:
            logger.warning(f"Wilcoxon failed for {feat}: {e}")
            continue
        median_diff = float(pair[col2].median() - pair[col1].median())
        mean_diff = float(pair[col2].mean() - pair[col1].mean())
        results.append({
            "feature": feat,
            "median_diff": median_diff,
            "mean_diff": mean_diff,
            "statistic": float(stat),
            "pvalue": float(pvalue),
        })

    result_df = pd.DataFrame(results)
    if result_df.empty:
        return {
            "significant_features": result_df,
            "volcano_plot": go.Figure(),
            "statistics": {
                "method": "paired_wilcoxon",
                "n_features_tested": 0,
                "n_significant": 0,
                "pvalue_threshold": pvalue_threshold,
            },
        }

    result_df["padj"] = adjust_pvalues(result_df["pvalue"].values, "fdr_bh")
    result_df["significant"] = result_df["padj"] < pvalue_threshold
    result_df = result_df.sort_values("padj")

    sig_df = result_df[result_df["significant"]].copy()

    fig = _build_volcano_plot(
        result_df,
        effect_col="median_diff",
        pval_col="pvalue",
        padj_col="padj",
        pvalue_threshold=pvalue_threshold,
        title=f"Paired Wilcoxon ({g1} vs {g2})",
    )

    stats_dict = {
        "method": "paired_wilcoxon",
        "transformation": transformation,
        "n_features_tested": int(len(result_df)),
        "n_significant": int(sig_df.shape[0]),
        "n_up": int((sig_df["median_diff"] > 0).sum()),
        "n_down": int((sig_df["median_diff"] < 0).sum()),
        "pvalue_threshold": pvalue_threshold,
        "groups": [g1, g2],
    }

    return {
        "significant_features": sig_df,
        "volcano_plot": fig,
        "statistics": stats_dict,
    }


def _run_paired_aldex2_r(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    subject_column: str,
    pvalue_threshold: float = 0.05,
) -> Optional[Dict[str, Any]]:
    """Run ALDEx2 via rpy2 for paired designs; returns None on failure."""
    if not R_AVAILABLE:
        return None

    try:
        importr("ALDEx2")
    except Exception as e:
        logger.warning(f"ALDEx2 R package not available: {e}")
        return None

    try:
        _validate_paired_structure(metadata_df, subject_column, group_column)
    except ValueError:
        return None

    common = df.columns.intersection(metadata_df.index)
    count_sub = df[common].astype(int)
    meta_sub = metadata_df.loc[common].copy()
    meta_sub[group_column] = meta_sub[group_column].astype(str)
    meta_sub[subject_column] = meta_sub[subject_column].astype(str)

    groups = sorted(meta_sub[group_column].dropna().unique())
    g1, g2 = groups[0], groups[1]

    with localconverter(ro.default_converter + pandas2ri.converter):
        r_counts = ro.conversion.py2rpy(count_sub)
        r_meta = ro.conversion.py2rpy(meta_sub)

        ro.r('''
        run_paired_aldex2 <- function(counts, coldata, group_var, subject_var, g1, g2) {
            library(ALDEx2)
            # Keep only the two groups
            keep <- coldata[[group_var]] %in% c(g1, g2)
            counts <- counts[, keep, drop=FALSE]
            coldata <- coldata[keep, , drop=FALSE]
            # Ensure paired order: subject sorted within group
            ord <- order(coldata[[subject_var]], coldata[[group_var]])
            counts <- counts[, ord, drop=FALSE]
            coldata <- coldata[ord, , drop=FALSE]
            # Run ALDEx2
            conds <- coldata[[group_var]]
            x <- aldex.clr(reads = counts, conds = conds, mc.samples = 128)
            res <- aldex.ttest(x, paired.test = TRUE)
            res$feature <- rownames(res)
            rownames(res) <- NULL
            # Rename for consistency
            res <- res[, c("feature", "we.ep", "we.eBH", "wi.ep", "wi.eBH",
                           "rab.all", "rab.win.g1", "rab.win.g2",
                           "diff.btw", "diff.win")]
            colnames(res)[2:5] <- c("we_pvalue", "we_padj", "wi_pvalue", "wi_padj")
            return(res)
        }
        ''')
        r_func = ro.r["run_paired_aldex2"]
        result_r = r_func(r_counts, r_meta, group_column, subject_column, g1, g2)
        result_df = ro.conversion.rpy2py(result_r)

    result_df = result_df.dropna(subset=["feature"])
    result_df["padj"] = result_df["wi_padj"]
    result_df["pvalue"] = result_df["wi_pvalue"]
    result_df["effect"] = result_df["diff.btw"]
    result_df["significant"] = result_df["padj"] < pvalue_threshold
    result_df = result_df.sort_values("padj")

    sig_df = result_df[result_df["significant"]].copy()

    fig = _build_volcano_plot(
        result_df,
        effect_col="effect",
        pval_col="pvalue",
        padj_col="padj",
        pvalue_threshold=pvalue_threshold,
        title=f"Paired ALDEx2 ({g1} vs {g2})",
    )

    return {
        "significant_features": sig_df,
        "volcano_plot": fig,
        "statistics": {
            "method": "paired_aldex2",
            "engine": "R::ALDEx2",
            "n_features_tested": int(len(result_df)),
            "n_significant": int(sig_df.shape[0]),
            "n_up": int((sig_df["effect"] > 0).sum()),
            "n_down": int((sig_df["effect"] < 0).sum()),
            "pvalue_threshold": pvalue_threshold,
            "groups": [g1, g2],
        },
    }


def run_paired_differential_test(
    df,
    metadata_df,
    group_column,
    subject_column,
    method="paired_wilcoxon",
    transformation="clr",
    pvalue_threshold=0.05,
):
    """Paired differential abundance test for repeated-measures designs.

    Parameters
    ----------
    df : pd.DataFrame
        Feature abundance table (features x samples).
    metadata_df : pd.DataFrame
        Sample metadata indexed by sample ID.
    group_column : str
        Column in metadata containing the 2-group factor.
    subject_column : str
        Column in metadata containing the subject ID (must have exactly 2
        samples per subject).
    method : str
        "paired_wilcoxon" or "paired_aldex2".
    transformation : str
        "clr" (default), "log", or "none".
    pvalue_threshold : float
        Significance threshold for BH-adjusted p-values.

    Returns
    -------
    dict
        {
            "significant_features": pd.DataFrame,
            "volcano_plot": plotly.graph_objects.Figure,
            "statistics": dict,
        }
    """
    method = method.lower()
    if method == "paired_aldex2":
        result = _run_paired_aldex2_r(
            df, metadata_df, group_column, subject_column, pvalue_threshold
        )
        if result is None:
            logger.warning("ALDEx2 R failed; falling back to paired_wilcoxon")
            return _run_paired_wilcoxon(
                df, metadata_df, group_column, subject_column, transformation, pvalue_threshold
            )
        return result

    # Default / fallback
    return _run_paired_wilcoxon(
        df, metadata_df, group_column, subject_column, transformation, pvalue_threshold
    )
