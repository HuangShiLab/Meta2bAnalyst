"""
Rarefaction Curve Analysis
===========================
Evaluate sequencing depth sufficiency for microbiome data.
Standard quality control plot in microbiome studies.

Reference: Qiime2 alpha-rarefaction
"""
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform

logger = logging.getLogger(__name__)


def run_rarefaction(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    group_column: Optional[str] = None,
    metrics: List[str] = None,
    max_depth: Optional[int] = None,
    steps: int = 20,
    iterations: int = 10,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """
    Generate rarefaction curves for alpha diversity metrics.

    Args:
        df: Count matrix (samples x taxa)
        metadata_df: Sample metadata
        group_column: Column in metadata for grouping
        metrics: List of alpha diversity metrics to compute
        max_depth: Maximum sequencing depth to rarefy to
        steps: Number of depth steps
        iterations: Number of subsampling iterations per depth
        random_seed: Random seed for reproducibility

    Returns:
        Dict with plot_data, statistics
    """
    rng = np.random.default_rng(random_seed)
    metrics = metrics or ["richness", "shannon", "simpson"]

    # Convert to counts if relative abundance
    sample_sums = df.sum(axis=1)
    is_relative = (sample_sums < 10).all()
    if is_relative:
        # Convert to pseudo-counts
        df_counts = (df * 10000).round().astype(int)
    else:
        df_counts = df.copy()

    sample_sums = df_counts.sum(axis=1)

    # Determine max depth
    if max_depth is None:
        max_depth = int(sample_sums.min())
    max_depth = min(max_depth, int(sample_sums.min()))
    if max_depth < 10:
        raise ValueError(f"Max depth too small ({max_depth}). Check data format.")

    # Depth steps (log scale for better visualization)
    depths = np.unique(np.logspace(0, np.log10(max_depth), steps).astype(int))
    depths = depths[depths > 0]

    # Compute rarefaction curves with pure-Python alpha diversity
    # (avoids skbio metric-name restrictions)
    metric_aliases = {
        'richness': 'observed',
        'shannon': 'shannon',
        'simpson': 'simpson',
    }

    def _calc_alpha(counts, metric_name):
        """Calculate alpha diversity for a single sample's counts."""
        counts = np.asarray(counts)
        total = counts.sum()
        if total == 0:
            return 0.0
        mn = metric_aliases.get(metric_name, metric_name)
        if mn == 'observed':
            return float((counts > 0).sum())
        elif mn == 'shannon':
            p = counts[counts > 0] / total
            return float(-np.sum(p * np.log(p)))
        elif mn == 'simpson':
            p = counts / total
            return float(1 - np.sum(p ** 2))
        else:
            return float((counts > 0).sum())

    results = {metric: {} for metric in metrics}
    sample_ids = df_counts.index.tolist()

    for depth in depths:
        for metric in metrics:
            results[metric][depth] = []

        for _ in range(iterations):
            # Subsample each sample to 'depth'
            for sid in sample_ids:
                counts = df_counts.loc[sid].values
                total = counts.sum()
                if total < depth:
                    probs = counts / total if total > 0 else np.ones_like(counts) / len(counts)
                    subsampled_counts = rng.multinomial(depth, probs)
                else:
                    probs = counts / total
                    subsampled_counts = rng.multinomial(depth, probs)

                for metric in metrics:
                    val = _calc_alpha(subsampled_counts, metric)
                    results[metric][depth].append(val)

    # Build Plotly figure
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    n_metrics = len(metrics)
    if n_metrics == 1:
        fig = go.Figure()
    else:
        fig = make_subplots(rows=1, cols=n_metrics, subplot_titles=[m.title() for m in metrics])

    colors = {
        'default': '#1e40af',
    }

    for i, metric in enumerate(metrics):
        col = i + 1 if n_metrics > 1 else 1
        row = 1

        if group_column and metadata_df is not None and group_column in metadata_df.columns:
            groups = metadata_df[group_column].unique()
            group_colors = {
                str(g): ['#1e40af', '#d97706', '#0f766e', '#dc2626', '#7c3aed', '#0891b2'][j % 6]
                for j, g in enumerate(sorted(groups))
            }

            for group in sorted(groups):
                group_samples = metadata_df[metadata_df[group_column] == group].index
                group_samples = [s for s in group_samples if s in sample_ids]
                if not group_samples:
                    continue

                # Average within group
                mean_vals = []
                std_vals = []
                for depth in depths:
                    vals = []
                    for sid in group_samples:
                        vals.extend(results[metric][int(depth)])
                    mean_vals.append(np.mean(vals))
                    std_vals.append(np.std(vals))

                fig.add_trace(
                    go.Scatter(
                        x=list(depths),
                        y=mean_vals,
                        mode='lines',
                        name=f'{group} (mean)',
                        line=dict(color=group_colors.get(str(group), '#999')),
                        showlegend=(i == 0),
                        legendgroup=str(group),
                    ),
                    row=row, col=col,
                )

                fig.add_trace(
                    go.Scatter(
                        x=list(depths) + list(depths)[::-1],
                        y=[m + s for m, s in zip(mean_vals, std_vals)] + [m - s for m, s in zip(mean_vals[::-1], std_vals[::-1])],
                        fill='toself',
                        fillcolor=group_colors.get(str(group), '#999') + '20',
                        line=dict(color='rgba(0,0,0,0)'),
                        name=f'{group} (±SD)',
                        showlegend=False,
                        legendgroup=str(group),
                        hoverinfo='skip',
                    ),
                    row=row, col=col,
                )
        else:
            # Individual sample lines
            for sid in sample_ids[:min(20, len(sample_ids))]:  # Limit to 20 samples
                mean_vals = [np.mean(results[metric][int(depth)]) for depth in depths]
                fig.add_trace(
                    go.Scatter(
                        x=list(depths),
                        y=mean_vals,
                        mode='lines',
                        name=sid,
                        line=dict(color='rgba(100,100,100,0.3)'),
                        showlegend=False,
                    ),
                    row=row, col=col,
                )

    fig.update_layout(
        title='Rarefaction Curves (Alpha Diversity vs Sequencing Depth)',
        xaxis_title='Sequencing Depth',
        yaxis_title='Alpha Diversity',
        template='plotly_white',
        width=800,
        height=500 if n_metrics == 1 else 450,
        legend_title_text='Group' if group_column else '',
    )

    if n_metrics > 1:
        for i in range(n_metrics):
            fig.update_xaxes(title_text='Sequencing Depth', row=1, col=i + 1)
            fig.update_yaxes(title_text='Alpha Diversity', row=1, col=i + 1)

    # Saturation check
    saturation = {}
    for metric in metrics:
        final_vals = [np.mean(results[metric][int(depths[-1])]) for _ in sample_ids]
        mid_vals = [np.mean(results[metric][int(depths[len(depths) // 2])]) for _ in sample_ids]
        if final_vals and mid_vals and np.mean(mid_vals) > 0:
            saturation[metric] = float(np.mean(final_vals) / np.mean(mid_vals))
        else:
            saturation[metric] = 1.0

    return {
        'plot_data': fig.to_dict(),
        'statistics': {
            'max_depth': int(max_depth),
            'n_steps': int(len(depths)),
            'n_iterations': iterations,
            'n_samples': len(sample_ids),
            'metrics': metrics,
            'saturation_ratio': saturation,
            'saturated': {m: s > 0.95 for m, s in saturation.items()},
        },
    }
