"""
Meta2bAnalyst - DMI (Degree of Microbial Individuality) Module
===============================================================
Quantifies how "individualized" each taxon is by comparing within-subject
microbiome similarity to between-subject similarity.

Concept:
  DMI(taxon) = mean(within-subject pairwise distance) / mean(between-subject pairwise distance)
  Lower DMI → more individualized (person-specific).

References:
  - Faith et al. 2013, PNAS 110:11982-11987 (personal microbiome concept)
  - Franzosa et al. 2015, Cell Host Microbe 18:676-682
"""
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.spatial.distance import pdist, squareform

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


def _bray_curtis_pairwise(df: pd.DataFrame) -> np.ndarray:
    """Compute Bray-Curtis distance matrix for sample rows."""
    rel = df.div(df.sum(axis=1), axis=0).fillna(0)
    return squareform(pdist(rel.values, metric="braycurtis"))


def _aitchison_pairwise(df: pd.DataFrame, pseudo_count: float = 1e-6) -> np.ndarray:
    """Compute Aitchison (CLR-based Euclidean) distance matrix."""
    df_pseudo = df.replace(0, pseudo_count)
    log_df = np.log(df_pseudo)
    clr = log_df.subtract(log_df.mean(axis=1), axis=0)
    return squareform(pdist(clr.values, metric="euclidean"))


def _compute_dmi_for_taxon(
    taxon_abund: np.ndarray,
    subjects: np.ndarray,
    distance_metric: str = "braycurtis",
) -> Tuple[float, int, int]:
    """Compute DMI for a single taxon across subjects.

    For a single taxon, we compute pairwise distances between all samples
    based on the abundance vector, then compare within- vs between-subject
    mean distances.

    Args:
        taxon_abund: 1D array of abundances per sample.
        subjects: 1D array of subject IDs per sample.
        distance_metric: 'braycurtis' or 'aitchison'.

    Returns:
        (dmi, n_within, n_between)
    """
    n = len(taxon_abund)
    if n < 2:
        return np.nan, 0, 0

    # Build a 1-feature DataFrame for distance computation
    df_tmp = pd.DataFrame({"taxon": taxon_abund})

    if distance_metric == "braycurtis":
        # For single-feature BC: |a-b|/(a+b)
        dist_mat = squareform(pdist(df_tmp.values, metric="braycurtis"))
    else:
        dist_mat = squareform(pdist(df_tmp.values, metric="euclidean"))

    within_dists = []
    between_dists = []

    for i in range(n):
        for j in range(i + 1, n):
            if subjects[i] == subjects[j]:
                within_dists.append(dist_mat[i, j])
            else:
                between_dists.append(dist_mat[i, j])

    if len(within_dists) == 0 or len(between_dists) == 0:
        return np.nan, len(within_dists), len(between_dists)

    within_mean = float(np.mean(within_dists))
    between_mean = float(np.mean(between_dists))

    if between_mean == 0:
        return np.nan, len(within_dists), len(between_dists)

    dmi = within_mean / between_mean
    return dmi, len(within_dists), len(between_dists)


def _compute_dmi_per_taxon_betadiv(
    df: pd.DataFrame,
    subjects: pd.Series,
    distance_metric: str = "braycurtis",
) -> pd.DataFrame:
    """Compute DMI using the full beta-diversity matrix (all taxa together).

    This computes DMI per taxon by comparing the overall community distance
    for samples from the same subject vs. different subjects, weighted by
    the presence/absence or abundance of each taxon.

    The more common approach in microbiome literature is taxon-specific DMI
    using the taxon's abundance profile as the distance basis.
    """
    common = df.index.intersection(subjects.index)
    df_aligned = df.loc[common]
    subj_arr = subjects.loc[common].values
    n_samples = len(common)

    # Compute full beta-diversity matrix
    if distance_metric == "braycurtis":
        dist_mat = _bray_curtis_pairwise(df_aligned)
    elif distance_metric == "aitchison":
        dist_mat = _aitchison_pairwise(df_aligned)
    else:
        dist_mat = _bray_curtis_pairwise(df_aligned)

    results = []
    for taxon in df_aligned.columns:
        abund = df_aligned[taxon].values
        # Only consider pairs where both samples have non-zero abundance
        # This aligns with the taxon-specific DMI concept
        within_dists = []
        between_dists = []

        for i in range(n_samples):
            for j in range(i + 1, n_samples):
                if abund[i] > 0 and abund[j] > 0:
                    if subj_arr[i] == subj_arr[j]:
                        within_dists.append(dist_mat[i, j])
                    else:
                        between_dists.append(dist_mat[i, j])

        n_within = len(within_dists)
        n_between = len(between_dists)
        if n_within == 0 or n_between == 0:
            results.append({
                "taxon": taxon,
                "dmi": np.nan,
                "n_within_pairs": n_within,
                "n_between_pairs": n_between,
                "within_mean": np.nan,
                "between_mean": np.nan,
            })
            continue

        w_mean = float(np.mean(within_dists))
        b_mean = float(np.mean(between_dists))
        dmi = w_mean / b_mean if b_mean > 0 else np.nan

        results.append({
            "taxon": taxon,
            "dmi": dmi,
            "n_within_pairs": n_within,
            "n_between_pairs": n_between,
            "within_mean": w_mean,
            "between_mean": b_mean,
        })

    return pd.DataFrame(results)


def _bootstrap_dmi(
    df: pd.DataFrame,
    subjects: pd.Series,
    n_bootstrap: int = 20,
    distance_metric: str = "braycurtis",
    rng: Optional[np.random.RandomState] = None,
) -> pd.DataFrame:
    """Bootstrap DMI by resampling subjects within their own samples.

    For each bootstrap iteration, we resample with replacement the samples
    within each subject, then recompute DMI per taxon.
    """
    if rng is None:
        rng = np.random.RandomState(seed=42)

    common = df.index.intersection(subjects.index)
    df_aligned = df.loc[common]
    subj_arr = subjects.loc[common]

    unique_subjects = subj_arr.unique()
    taxa = df_aligned.columns.tolist()
    bootstrap_results = {t: [] for t in taxa}

    for b in range(n_bootstrap):
        # Resample within each subject
        resampled_indices = []
        for subj in unique_subjects:
            subj_mask = subj_arr == subj
            subj_samples = common[subj_mask]
            n_subj = len(subj_samples)
            if n_subj == 0:
                continue
            # Resample with replacement within subject
            chosen = rng.choice(subj_samples, size=n_subj, replace=True)
            resampled_indices.extend(chosen)

        if len(resampled_indices) < 2:
            continue

        resampled_df = df_aligned.loc[resampled_indices]
        resampled_subjects = subj_arr.loc[resampled_indices]

        dmi_df = _compute_dmi_per_taxon_betadiv(resampled_df, resampled_subjects, distance_metric)
        for _, row in dmi_df.iterrows():
            if not np.isnan(row["dmi"]):
                bootstrap_results[row["taxon"]].append(row["dmi"])

    ci_rows = []
    for taxon in taxa:
        vals = bootstrap_results[taxon]
        if len(vals) < 2:
            ci_rows.append({
                "taxon": taxon,
                "ci_lower": np.nan,
                "ci_upper": np.nan,
                "ci_95": [np.nan, np.nan],
                "bootstrap_mean": np.nan,
                "n_successful": len(vals),
            })
        else:
            ci_lower = float(np.percentile(vals, 2.5))
            ci_upper = float(np.percentile(vals, 97.5))
            ci_rows.append({
                "taxon": taxon,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
                "ci_95": [ci_lower, ci_upper],
                "bootstrap_mean": float(np.mean(vals)),
                "n_successful": len(vals),
            })

    return pd.DataFrame(ci_rows)


def _plot_dmi_distribution(dmi_df: pd.DataFrame, ci_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Generate DMI distribution and per-taxon point plots."""
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("DMI Distribution", "Top Taxa DMI (with 95% CI)"),
        column_widths=[0.4, 0.6],
    )

    valid_dmi = dmi_df["dmi"].dropna()

    # Histogram
    fig.add_trace(
        go.Histogram(
            x=valid_dmi,
            nbinsx=30,
            marker_color="#1f77b4",
            opacity=0.75,
            name="DMI",
            hovertemplate="DMI: %{x:.3f}<br>Count: %{y}<extra></extra>",
        ),
        row=1, col=1,
    )

    # Add median line
    median_dmi = float(valid_dmi.median())
    fig.add_vline(
        x=median_dmi,
        line_dash="dash",
        line_color="red",
        line_width=2,
        annotation_text=f"median={median_dmi:.3f}",
        annotation_position="top",
        row=1, col=1,
    )

    # Top taxa point plot with CI
    plot_df = dmi_df.copy()
    if ci_df is not None and not ci_df.empty:
        plot_df = plot_df.merge(ci_df[["taxon", "ci_lower", "ci_upper"]], on="taxon", how="left")
    else:
        plot_df["ci_lower"] = np.nan
        plot_df["ci_upper"] = np.nan

    # Sort by DMI and take top 30
    plot_df = plot_df.dropna(subset=["dmi"]).sort_values("dmi").head(30)
    y_positions = list(range(len(plot_df)))

    # Error bars if CI available
    if "ci_lower" in plot_df.columns and plot_df["ci_lower"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=plot_df["dmi"],
                y=y_positions,
                mode="markers",
                error_x=dict(
                    type="data",
                    symmetric=False,
                    array=plot_df["ci_upper"] - plot_df["dmi"],
                    arrayminus=plot_df["dmi"] - plot_df["ci_lower"],
                    visible=True,
                    color="#7f7f7f",
                ),
                marker=dict(size=10, color="#2ca02c", line=dict(width=1, color="black")),
                name="DMI ± 95% CI",
                hovertemplate="%{customdata}<br>DMI: %{x:.3f}<extra></extra>",
                customdata=plot_df["taxon"].values,
            ),
            row=1, col=2,
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=plot_df["dmi"],
                y=y_positions,
                mode="markers",
                marker=dict(size=10, color="#2ca02c", line=dict(width=1, color="black")),
                name="DMI",
                hovertemplate="%{customdata}<br>DMI: %{x:.3f}<extra></extra>",
                customdata=plot_df["taxon"].values,
            ),
            row=1, col=2,
        )

    fig.update_yaxes(
        tickmode="array",
        tickvals=y_positions,
        ticktext=plot_df["taxon"].values,
        row=1, col=2,
    )

    fig.update_layout(
        title="Degree of Microbial Individuality (DMI)",
        template="plotly_white",
        width=1200,
        height=max(500, min(800, len(plot_df) * 20)),
        showlegend=False,
    )
    fig.update_xaxes(title_text="DMI (lower = more individualized)", row=1, col=1)
    fig.update_xaxes(title_text="DMI (lower = more individualized)", row=1, col=2)
    fig.update_yaxes(title_text="Taxon", row=1, col=2)

    return fig.to_dict()


# ─────────────────────────────── Main Runner

def run_dmi(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    subject_column: str,
    time_column: Optional[str] = None,
    n_bootstrap: int = 20,
    distance_metric: str = "braycurtis",
) -> Dict[str, Any]:
    """Compute Degree of Microbial Individuality (DMI) per taxon.

    DMI = mean(within-subject distance) / mean(between-subject distance).
    Lower DMI indicates a taxon is more person-specific.

    Args:
        df: Feature table (samples x taxa).
        metadata_df: Metadata DataFrame indexed by sample ID.
        subject_column: Column identifying subjects/individuals.
        time_column: Optional timepoint column (ignored in current implementation
                     but reserved for temporal stratification).
        n_bootstrap: Number of bootstrap iterations for CI.
        distance_metric: 'braycurtis' or 'aitchison'.

    Returns:
        Dict with:
            - dmi_values: DataFrame of per-taxon DMI.
            - bootstrap_ci: DataFrame of 95% CIs.
            - plot_data: Plotly JSON figure.
    """
    logger.info(f"Starting DMI analysis: subject_column={subject_column}, n_bootstrap={n_bootstrap}")

    common = df.index.intersection(metadata_df.index)
    if len(common) == 0:
        raise ValueError("No matching samples between data and metadata.")

    if subject_column not in metadata_df.columns:
        raise ValueError(f"Subject column '{subject_column}' not found in metadata.")

    subjects = metadata_df.loc[common, subject_column]
    n_subjects = subjects.nunique()
    if n_subjects < 2:
        raise ValueError(f"Need at least 2 subjects, found {n_subjects}.")

    # Compute DMI per taxon
    dmi_df = _compute_dmi_per_taxon_betadiv(df.loc[common], subjects, distance_metric)

    # Bootstrap CI
    ci_df = pd.DataFrame()
    if n_bootstrap > 0:
        logger.info(f"Running {n_bootstrap} bootstrap iterations for DMI CI")
        ci_df = _bootstrap_dmi(df.loc[common], subjects, n_bootstrap, distance_metric)

    # Merge CI into dmi_df
    if not ci_df.empty:
        dmi_df = dmi_df.merge(ci_df, on="taxon", how="left")

    # Summary statistics
    valid_dmi = dmi_df["dmi"].dropna()
    summary = {
        "median_dmi": float(valid_dmi.median()) if len(valid_dmi) > 0 else None,
        "mean_dmi": float(valid_dmi.mean()) if len(valid_dmi) > 0 else None,
        "std_dmi": float(valid_dmi.std()) if len(valid_dmi) > 0 else None,
        "min_dmi": float(valid_dmi.min()) if len(valid_dmi) > 0 else None,
        "max_dmi": float(valid_dmi.max()) if len(valid_dmi) > 0 else None,
        "n_taxa": int(len(dmi_df)),
        "n_subjects": int(n_subjects),
        "n_samples": int(len(common)),
        "distance_metric": distance_metric,
    }

    # Plot
    plot_data = _plot_dmi_distribution(dmi_df, ci_df if not ci_df.empty else None)

    result = {
        "dmi_values": _sanitize_json(dmi_df),
        "bootstrap_ci": _sanitize_json(ci_df),
        "plot_data": plot_data,
        "summary": summary,
        "subject_column": subject_column,
        "time_column": time_column,
        "n_bootstrap": n_bootstrap,
    }

    logger.info("DMI analysis complete")
    return result
