"""
Meta2bAnalyst - ICC Stability Module
====================================
Intraclass Correlation Coefficient (ICC) for microbiome temporal stability.

ICC(1,1) = between-subject variance / (between-subject variance + within-subject variance)
Ranges:
  <0.50   → low
  0.50-0.75 → moderate
  0.75-0.90 → good
  >0.90   → excellent

References:
  - Koo & Li 2016, J Chiropr Med 15:155-163 (ICC guidelines)
  - Falony et al. 2016, Science 352:560-564 (temporal stability)
"""
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=RuntimeWarning)


def _sanitize_json(obj: Any) -> Any:
    """Recursively convert numpy/pandas types to native Python types."""
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
        return _sanitize_json(obj.to_dict(orient="records"))
    if isinstance(obj, pd.Series):
        return _sanitize_json(obj.to_dict())
    return obj


def _clr_transform(df: pd.DataFrame, pseudo_count: float = 1e-6) -> pd.DataFrame:
    """Centered log-ratio transformation."""
    df_pseudo = df.replace(0, pseudo_count)
    log_df = np.log(df_pseudo)
    return log_df.subtract(log_df.mean(axis=1), axis=0)


def _log_transform(df: pd.DataFrame, pseudo_count: float = 1e-6) -> pd.DataFrame:
    """Simple log transformation."""
    return np.log(df.replace(0, pseudo_count))


def _transform(df: pd.DataFrame, method: str) -> pd.DataFrame:
    """Apply the specified transformation."""
    if method == "clr":
        return _clr_transform(df)
    elif method == "log":
        return _log_transform(df)
    elif method == "sqrt":
        return np.sqrt(df)
    elif method == "asinh":
        return np.arcsinh(df)
    elif method == "none":
        return df.copy()
    else:
        return _clr_transform(df)


def _icc_oneway_random(
    values: np.ndarray,
    subjects: np.ndarray,
) -> Tuple[float, Dict[str, float]]:
    """Compute ICC(1,1) for one-way random effects model.

    Uses ANOVA decomposition:
      MS_between = n_obs_per_subj * Var(between) + Var(within)
      MS_within  = Var(within)
      ICC = (MS_between - MS_within) / (MS_between + (n_obs - 1) * MS_within)

    For unbalanced designs, we use the average number of observations per subject.

    Args:
        values: Measurement values (e.g., abundance of one taxon).
        subjects: Subject IDs corresponding to values.

    Returns:
        (icc, dict with ms_between, ms_within, n_subjects, n_obs_mean)
    """
    df = pd.DataFrame({"value": values, "subject": subjects})
    # Drop NaNs
    df = df.dropna()
    if len(df) < 2:
        return np.nan, {}

    unique_subjects = df["subject"].unique()
    n_subjects = len(unique_subjects)
    if n_subjects < 2:
        return np.nan, {}

    # Group means and sizes
    group_stats = df.groupby("subject")["value"].agg(["mean", "count", "var"])
    group_means = group_stats["mean"].values
    group_counts = group_stats["count"].values
    n_total = len(df)
    n_obs_mean = float(group_counts.mean())

    # Grand mean
    grand_mean = df["value"].mean()

    # SS_between and SS_within
    ss_between = np.sum(group_counts * (group_means - grand_mean) ** 2)
    ss_within = 0.0
    for subj in unique_subjects:
        subj_vals = df[df["subject"] == subj]["value"].values
        subj_mean = subj_vals.mean()
        ss_within += np.sum((subj_vals - subj_mean) ** 2)

    df_between = n_subjects - 1
    df_within = n_total - n_subjects

    ms_between = ss_between / df_between if df_between > 0 else 0.0
    ms_within = ss_within / df_within if df_within > 0 else 0.0

    # ICC(1,1) for unbalanced design (using average n)
    if ms_within <= 0:
        # All variance is between subjects
        icc = 1.0 if ms_between > 0 else np.nan
    else:
        icc = (ms_between - ms_within) / (ms_between + (n_obs_mean - 1) * ms_within)

    # Clamp to [0, 1] for interpretability
    if not np.isnan(icc):
        icc = max(0.0, min(1.0, icc))

    return float(icc), {
        "ms_between": float(ms_between),
        "ms_within": float(ms_within),
        "n_subjects": int(n_subjects),
        "n_obs_mean": float(n_obs_mean),
        "n_total": int(n_total),
    }


def _icc_pingouin(
    values: np.ndarray,
    subjects: np.ndarray,
) -> Tuple[float, Dict[str, float]]:
    """Try to compute ICC using pingouin if available."""
    try:
        import pingouin as pg
        df = pd.DataFrame({"value": values, "subject": subjects})
        df = df.dropna()
        if len(df) < 2 or df["subject"].nunique() < 2:
            return np.nan, {}
        # pingouin expects targets and raters; here subject = target, occasion = rater
        # We model each observation as a separate "rater" occasion within subject
        df = df.sort_values("subject").reset_index(drop=True)
        df["occasion"] = df.groupby("subject").cumcount()
        icc_result = pg.intraclass_corr(
            data=df, targets="subject", raters="occasion", ratings="value"
        )
        # ICC1 = single_rater_absolute (one-way random)
        icc1_row = icc_result[icc_result["Type"] == "ICC1"]
        if len(icc1_row) > 0:
            icc_val = float(icc1_row["ICC"].values[0])
            ci_lower = float(icc1_row["CI95%"].values[0][0]) if "CI95%" in icc1_row.columns else np.nan
            ci_upper = float(icc1_row["CI95%"].values[0][1]) if "CI95%" in icc1_row.columns else np.nan
            return icc_val, {"ci_lower": ci_lower, "ci_upper": ci_upper, "source": "pingouin"}
        # Fallback: use ICC2 or first available
        icc_val = float(icc_result["ICC"].values[0])
        return icc_val, {"source": "pingouin_fallback"}
    except ImportError:
        return np.nan, {"source": "pingouin_not_available"}
    except Exception as e:
        logger.debug(f"pingouin ICC failed: {e}")
        return np.nan, {"source": "pingouin_error", "error": str(e)}


def _icc_grade(icc: float) -> str:
    """Map ICC value to reliability grade."""
    if np.isnan(icc):
        return "unknown"
    if icc < 0.5:
        return "low"
    if icc < 0.75:
        return "moderate"
    if icc < 0.9:
        return "good"
    return "excellent"


def _compute_icc_per_taxon(
    df: pd.DataFrame,
    subjects: pd.Series,
    transformation: str = "clr",
    prefer_pingouin: bool = True,
) -> pd.DataFrame:
    """Compute ICC per taxon across subjects."""
    common = df.index.intersection(subjects.index)
    df_aligned = df.loc[common]
    subj_arr = subjects.loc[common]

    # Apply transformation
    df_trans = _transform(df_aligned, transformation)

    results = []
    for taxon in df_trans.columns:
        values = df_trans[taxon].values

        icc_val = np.nan
        details = {}

        # Try pingouin first if requested
        if prefer_pingouin:
            icc_val, details = _icc_pingouin(values, subj_arr.values)

        # Fallback to manual ANOVA-based ICC
        if np.isnan(icc_val):
            icc_val, details = _icc_oneway_random(values, subj_arr.values)

        grade = _icc_grade(icc_val)

        results.append({
            "taxon": taxon,
            "icc": icc_val,
            "grade": grade,
            "n_subjects": details.get("n_subjects", int(subj_arr.nunique())),
            "n_obs_mean": details.get("n_obs_mean", np.nan),
            "ms_between": details.get("ms_between", np.nan),
            "ms_within": details.get("ms_within", np.nan),
            "ci_lower": details.get("ci_lower", np.nan),
            "ci_upper": details.get("ci_upper", np.nan),
            "source": details.get("source", "manual"),
        })

    return pd.DataFrame(results)


def _plot_icc_distribution(icc_df: pd.DataFrame, time_column: Optional[str] = None) -> Dict[str, Any]:
    """Generate ICC distribution histogram + grade pie chart + optional time series."""
    valid_icc = icc_df["icc"].dropna()

    if time_column:
        # 3 subplots: histogram, pie, time series placeholder
        fig = make_subplots(
            rows=1, cols=3,
            subplot_titles=("ICC Distribution", "Stability Grade", "Temporal Trend (placeholder)"),
            specs=[[{"type": "xy"}, {"type": "pie"}, {"type": "xy"}]],
            column_widths=[0.35, 0.30, 0.35],
        )
    else:
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=("ICC Distribution", "Stability Grade"),
            specs=[[{"type": "xy"}, {"type": "pie"}]],
            column_widths=[0.5, 0.5],
        )

    # Histogram
    fig.add_trace(
        go.Histogram(
            x=valid_icc,
            nbinsx=25,
            marker_color="#1f77b4",
            opacity=0.75,
            name="ICC",
            hovertemplate="ICC: %{x:.3f}<br>Count: %{y}<extra></extra>",
        ),
        row=1, col=1,
    )

    # Grade reference lines
    for threshold, color, label in [(0.5, "red", "low"), (0.75, "orange", "moderate"), (0.9, "green", "good")]:
        fig.add_vline(
            x=threshold,
            line_dash="dash",
            line_color=color,
            line_width=1,
            row=1, col=1,
        )

    # Pie chart
    grade_counts = icc_df["grade"].value_counts().to_dict()
    # Ensure all grades appear
    all_grades = ["low", "moderate", "good", "excellent", "unknown"]
    pie_labels = []
    pie_values = []
    pie_colors = ["#d62728", "#ff7f0e", "#2ca02c", "#1f77b4", "#7f7f7f"]
    for g in all_grades:
        if g in grade_counts:
            pie_labels.append(g)
            pie_values.append(grade_counts[g])

    fig.add_trace(
        go.Pie(
            labels=pie_labels,
            values=pie_values,
            marker_colors=pie_colors[:len(pie_labels)],
            textinfo="label+percent",
            hole=0.3,
            name="Grade",
        ),
        row=1, col=2,
    )

    # Temporal trend placeholder (if time_column provided)
    if time_column:
        fig.add_trace(
            go.Scatter(
                x=[0, 1],
                y=[0, 1],
                mode="markers",
                marker=dict(size=1, color="white"),
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1, col=3,
        )
        fig.update_xaxes(title_text="Time", row=1, col=3)
        fig.update_yaxes(title_text="Abundance (placeholder)", row=1, col=3)

    fig.update_layout(
        title="Microbiome Temporal Stability (ICC)",
        template="plotly_white",
        width=1200 if time_column else 900,
        height=500,
        showlegend=False,
    )
    fig.update_xaxes(title_text="ICC(1,1)", row=1, col=1)
    fig.update_yaxes(title_text="Number of Taxa", row=1, col=1)

    return fig.to_dict()


def _plot_taxon_time_series(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    subject_column: str,
    time_column: str,
    top_n_taxa: int = 10,
) -> Dict[str, Any]:
    """Plot time series for top-N most stable taxa (highest ICC)."""
    common = df.index.intersection(metadata_df.index)
    df_aligned = df.loc[common]
    meta = metadata_df.loc[common]

    if time_column not in meta.columns:
        return go.Figure().update_layout(title=f"Time column '{time_column}' not found").to_dict()

    # Try to make time numeric
    try:
        time_vals = pd.to_numeric(meta[time_column])
    except (ValueError, TypeError):
        time_vals = pd.Series(
            pd.Categorical(meta[time_column], categories=sorted(meta[time_column].dropna().unique()), ordered=True).codes,
            index=meta.index,
        )

    # Compute ICC per taxon to pick top stable
    from app.services.icc_stability import _compute_icc_per_taxon  # local import to avoid circular if any
    icc_df = _compute_icc_per_taxon(df_aligned, meta[subject_column], transformation="clr")
    top_taxa = icc_df.dropna(subset=["icc"]).sort_values("icc", ascending=False).head(top_n_taxa)["taxon"].tolist()

    fig = go.Figure()
    colors = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]

    for idx, taxon in enumerate(top_taxa):
        color = colors[idx % len(colors)]
        for subj in meta[subject_column].unique():
            mask = meta[subject_column] == subj
            sub_times = time_vals.loc[mask].sort_values()
            sub_abund = df_aligned.loc[sub_times.index, taxon].values
            fig.add_trace(go.Scatter(
                x=sub_times.values,
                y=sub_abund,
                mode="lines+markers",
                line=dict(color=color, width=1),
                marker=dict(size=5, color=color),
                name=f"{taxon} ({subj})",
                legendgroup=taxon,
                showlegend=True if subj == meta[subject_column].unique()[0] else False,
                hovertemplate=f"{taxon}<br>Time: %{{x}}<br>Abund: %{{y:.3f}}<extra></extra>",
            ))

    fig.update_layout(
        title=f"Temporal Trajectories (Top {top_n_taxa} Stable Taxa)",
        xaxis_title=time_column,
        yaxis_title="Abundance",
        template="plotly_white",
        width=1000,
        height=600,
        legend=dict(orientation="h", yanchor="bottom", y=-0.3),
    )

    return fig.to_dict()


# ─────────────────────────────── Main Runner

def run_icc_stability(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    subject_column: str,
    time_column: Optional[str] = None,
    transformation: str = "clr",
) -> Dict[str, Any]:
    """Compute ICC for microbiome temporal stability per taxon.

    ICC(1,1) quantifies the proportion of variance attributable to
    between-subject differences vs. within-subject (temporal) variation.

    Args:
        df: Feature table (samples x taxa).
        metadata_df: Metadata DataFrame indexed by sample ID.
        subject_column: Column identifying subjects/individuals.
        time_column: Optional timepoint column for temporal visualization.
        transformation: Data transformation before ICC ('clr', 'log', 'sqrt', 'asinh', 'none').

    Returns:
        Dict with:
            - icc_values: DataFrame of per-taxon ICC.
            - stability_grade: Counts per grade.
            - plot_data: Plotly JSON figure.
            - time_series_plot: Plotly JSON (if time_column provided).
    """
    logger.info(f"Starting ICC stability analysis: subject_column={subject_column}, transformation={transformation}")

    common = df.index.intersection(metadata_df.index)
    if len(common) == 0:
        raise ValueError("No matching samples between data and metadata.")

    if subject_column not in metadata_df.columns:
        raise ValueError(f"Subject column '{subject_column}' not found in metadata.")

    subjects = metadata_df.loc[common, subject_column]
    n_subjects = subjects.nunique()
    if n_subjects < 2:
        raise ValueError(f"Need at least 2 subjects, found {n_subjects}.")

    # Compute ICC per taxon
    icc_df = _compute_icc_per_taxon(df.loc[common], subjects, transformation)

    # Grade counts
    grade_counts = icc_df["grade"].value_counts().to_dict()
    stability_grade = {
        "counts": grade_counts,
        "percentages": {k: round(v / len(icc_df) * 100, 2) for k, v in grade_counts.items()},
    }

    # Summary stats
    valid_icc = icc_df["icc"].dropna()
    summary = {
        "median_icc": float(valid_icc.median()) if len(valid_icc) > 0 else None,
        "mean_icc": float(valid_icc.mean()) if len(valid_icc) > 0 else None,
        "n_taxa": int(len(icc_df)),
        "n_subjects": int(n_subjects),
        "n_samples": int(len(common)),
        "transformation": transformation,
    }

    # Plots
    plot_data = _plot_icc_distribution(icc_df, time_column=time_column)

    result = {
        "icc_values": _sanitize_json(icc_df),
        "stability_grade": stability_grade,
        "plot_data": plot_data,
        "summary": summary,
        "subject_column": subject_column,
        "time_column": time_column,
    }

    # Optional time series plot
    if time_column and time_column in metadata_df.columns:
        result["time_series_plot"] = _plot_taxon_time_series(
            df.loc[common], metadata_df.loc[common], subject_column, time_column
        )
    else:
        result["time_series_plot"] = None

    logger.info("ICC stability analysis complete")
    return result
