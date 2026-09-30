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


def _prepare_pairs(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    subject_column: str,
    groups: Optional[List[str]] = None,
) -> tuple:
    """Select complete subject pairs for a two-level comparison.

    Args:
        df: Feature table, features x samples.
        metadata_df: Sample metadata indexed by sample ID.
        group_column: Factor defining the two conditions (e.g. Visit).
        subject_column: Participant identifier used for pairing.
        groups: The two levels to compare, reference first. Required when the
            factor has more than two levels (e.g. ["T4", "T9"] out of seven
            visits); defaults to the two levels, sorted.

    Returns:
        (samples_g1, samples_g2, g1, g2, n_dropped): aligned sample-ID lists,
        one entry per subject with exactly one sample at each level, and the
        number of subjects dropped for lacking a complete pair.
    """
    for col in (subject_column, group_column):
        if not col or col not in metadata_df.columns:
            raise ValueError(f"column '{col}' not found in metadata")

    common = df.columns.intersection(metadata_df.index)
    meta = metadata_df.loc[common, [subject_column, group_column]].dropna().astype(str)

    levels = sorted(meta[group_column].unique())
    if groups is not None:
        groups = [str(g) for g in groups]
        if len(groups) != 2:
            raise ValueError(f"groups must name exactly two levels, got {groups}")
        missing = [g for g in groups if g not in levels]
        if missing:
            raise ValueError(f"level(s) {missing} not found in '{group_column}' (have {levels})")
        g1, g2 = groups
    elif len(levels) == 2:
        g1, g2 = levels
    else:
        raise ValueError(
            f"'{group_column}' has {len(levels)} levels {levels}; pass groups=[reference, comparison] "
            "to choose the two to compare."
        )

    meta = meta[meta[group_column].isin([g1, g2])]
    counts = meta.groupby([subject_column, group_column]).size()
    if (counts > 1).any():
        dup = counts[counts > 1].index.tolist()[:5]
        raise ValueError(
            f"Some subjects have more than one sample at the same level (e.g. {dup}); "
            "pairing is ambiguous. Aggregate or remove replicates first."
        )
    per_subject = meta.groupby(subject_column)[group_column].nunique()
    complete = per_subject[per_subject == 2].index
    n_dropped = int((per_subject < 2).sum())
    if len(complete) < 3:
        raise ValueError(
            f"Only {len(complete)} subjects have samples at both '{g1}' and '{g2}'; "
            "a paired test needs at least 3."
        )
    meta = meta[meta[subject_column].isin(complete)].sort_values(subject_column)
    s1 = meta.index[meta[group_column] == g1].tolist()
    s2 = meta.index[meta[group_column] == g2].tolist()
    return s1, s2, g1, g2, n_dropped


def _run_paired_wilcoxon(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    subject_column: str,
    transformation: str = "clr",
    pvalue_threshold: float = 0.05,
    groups: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Paired Wilcoxon signed-rank test per feature (effect = g2 - g1)."""
    s1, s2, g1, g2, n_dropped = _prepare_pairs(df, metadata_df, group_column, subject_column, groups)

    X = df[s1 + s2].T  # samples x features, the orientation _clr_transform expects
    if transformation.lower() == "clr":
        X_trans = _clr_transform(X)
    elif transformation.lower() == "log":
        X_trans = np.log1p(X)
    elif transformation.lower() == "none":
        X_trans = X
    else:
        raise ValueError(f"Unknown transformation: {transformation}")

    A = X_trans.loc[s1].to_numpy(dtype=float)  # subjects x features, level g1
    B = X_trans.loc[s2].to_numpy(dtype=float)  # same subjects, level g2

    results = []
    for j, feat in enumerate(X_trans.columns):
        a, b = A[:, j], B[:, j]
        diff = b - a
        if np.allclose(diff, 0):
            continue  # identical in every pair: the signed-rank test is undefined
        try:
            stat, pvalue = stats.wilcoxon(a, b, alternative="two-sided")
        except Exception as e:
            logger.warning(f"Wilcoxon failed for {feat}: {e}")
            continue
        results.append({
            "feature": str(feat),
            "median_diff": float(np.median(diff)),
            "mean_diff": float(np.mean(diff)),
            "statistic": float(stat),
            "pvalue": float(pvalue),
        })

    stats_dict = {
        "method": "paired_wilcoxon",
        "engine": "python::scipy.stats.wilcoxon",
        "transformation": transformation,
        "groups": [g1, g2],
        "effect_direction": f"{g2} minus {g1}",
        "n_pairs": len(s1),
        "n_subjects_dropped_incomplete": n_dropped,
        "pvalue_threshold": pvalue_threshold,
    }
    result_df = pd.DataFrame(results)
    if result_df.empty:
        stats_dict.update({"n_features_tested": 0, "n_significant": 0, "n_up": 0, "n_down": 0})
        return {"significant_features": result_df, "results": result_df,
                "volcano_plot": go.Figure(), "statistics": stats_dict}

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
    stats_dict.update({
        "n_features_tested": int(len(result_df)),
        "n_significant": int(sig_df.shape[0]),
        "n_up": int((sig_df["median_diff"] > 0).sum()),
        "n_down": int((sig_df["median_diff"] < 0).sum()),
    })
    return {
        "significant_features": sig_df,
        "results": result_df,
        "volcano_plot": fig,
        "statistics": stats_dict,
    }


def _run_paired_aldex2_r(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    subject_column: str,
    pvalue_threshold: float = 0.05,
    groups: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Run ALDEx2 via rpy2 for paired designs; returns None if R/ALDEx2 is unavailable."""
    if not R_AVAILABLE:
        return None

    try:
        importr("ALDEx2")
    except Exception as e:
        logger.warning(f"ALDEx2 R package not available: {e}")
        return None

    s1, s2, g1, g2, _ = _prepare_pairs(df, metadata_df, group_column, subject_column, groups)
    common = s1 + s2
    count_sub = df[common].astype(int)
    meta_sub = metadata_df.loc[common].copy()
    meta_sub[group_column] = meta_sub[group_column].astype(str)
    meta_sub[subject_column] = meta_sub[subject_column].astype(str)

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
            # aldex.ttest returns only the p-value columns; rab.*/diff.*/effect
            # come from aldex.effect. The old code selected effect columns straight
            # off aldex.ttest's output ("undefined columns selected").
            conds <- coldata[[group_var]]
            x <- aldex.clr(reads = counts, conds = conds, mc.samples = 128)
            res <- cbind(aldex.ttest(x, paired.test = TRUE), aldex.effect(x))
            res$feature <- rownames(res)
            rownames(res) <- NULL
            # rab.win columns carry the *actual* condition names (rab.win.T4),
            # not g1/g2 -- normalize them when present.
            for (pair in list(c(make.names(paste0("rab.win.", g1)), "rab.win.g1"),
                              c(make.names(paste0("rab.win.", g2)), "rab.win.g2"))) {
                if (pair[1] %in% colnames(res)) colnames(res)[colnames(res) == pair[1]] <- pair[2]
            }
            want <- c("feature", "we.ep", "we.eBH", "wi.ep", "wi.eBH", "rab.all",
                      "rab.win.g1", "rab.win.g2", "diff.btw", "diff.win", "effect")
            res[, intersect(want, colnames(res)), drop = FALSE]
        }
        ''')
        r_func = ro.r["run_paired_aldex2"]
        result_r = r_func(r_counts, r_meta, group_column, subject_column, g1, g2)
        result_df = ro.conversion.rpy2py(result_r)

    result_df = result_df.dropna(subset=["feature"])
    # Prefer the paired Wilcoxon columns; fall back to Welch's when the
    # installed ALDEx2 does not provide them. Keyed by name, not position.
    if "wi.ep" in result_df.columns and "wi.eBH" in result_df.columns:
        result_df["pvalue"] = result_df["wi.ep"]
        result_df["padj"] = result_df["wi.eBH"]
    else:
        result_df["pvalue"] = result_df["we.ep"]
        result_df["padj"] = result_df["we.eBH"]
    if "effect" not in result_df.columns:
        result_df["effect"] = result_df.get("diff.btw")
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
        "results": result_df,
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
    groups=None,
    allow_approximation=False,
):
    """Paired differential abundance test for repeated-measures designs.

    Parameters
    ----------
    df : pd.DataFrame
        Feature abundance table (features x samples).
    metadata_df : pd.DataFrame
        Sample metadata indexed by sample ID.
    group_column : str
        Factor defining the conditions (may have more than two levels).
    subject_column : str
        Participant ID used for pairing.
    method : str
        "paired_wilcoxon" (CLR + Wilcoxon signed-rank) or "paired_aldex2" (R).
    transformation : str
        "clr" (default), "log", or "none" (paired_wilcoxon only).
    pvalue_threshold : float
        Significance threshold for BH-adjusted p-values.
    groups : list[str] | None
        [reference, comparison] levels; required if group_column has >2 levels.
        Subjects without a sample at both levels are dropped and counted.
    allow_approximation : bool
        paired_aldex2 without R: refuse (default) or run the paired Wilcoxon
        test labelled as an approximation.

    Returns
    -------
    dict with "significant_features", "results" (all features), "volcano_plot"
    and "statistics" (including engine and the pairing summary).
    """
    method = method.lower()
    if method == "paired_aldex2":
        result = _run_paired_aldex2_r(
            df, metadata_df, group_column, subject_column, pvalue_threshold, groups
        )
        if result is not None:
            return result
        if not allow_approximation:
            raise ValueError(
                "paired_aldex2 requires the R package ALDEx2, which is not available on "
                "this server. Use method='paired_wilcoxon', or resend with "
                "allow_approximation=true to run the paired Wilcoxon test labelled as an "
                "approximation (results must not be reported as ALDEx2)."
            )
        result = _run_paired_wilcoxon(
            df, metadata_df, group_column, subject_column, transformation, pvalue_threshold, groups
        )
        result["statistics"].update({
            "engine": "python-approx::paired_aldex2",
            "is_approximation": True,
            "approximation_note": "CLR point estimate + paired Wilcoxon; no Monte-Carlo Dirichlet sampling.",
        })
        return result
    if method != "paired_wilcoxon":
        raise ValueError(f"Unknown method '{method}' (use paired_wilcoxon or paired_aldex2)")
    return _run_paired_wilcoxon(
        df, metadata_df, group_column, subject_column, transformation, pvalue_threshold, groups
    )
