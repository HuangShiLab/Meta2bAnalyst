"""
Meta2bAnalyst - Core Microbiome Analysis
Identifies taxa present in most samples. Important for dysbiosis studies
and defining stable community members.
"""
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)


def run_core_microbiome(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    group_column: Optional[str] = None,
    prevalence_threshold: float = 0.5,
    abundance_threshold: float = 0.01,
) -> Dict[str, Any]:
    """Identify core microbiome taxa based on prevalence and abundance thresholds.

    Args:
        df: Feature table (features x samples) with relative or count abundances.
        metadata_df: Optional metadata for group-wise core analysis.
        group_column: Optional metadata column for per-group core calculation.
        prevalence_threshold: Minimum fraction of samples a taxon must be present in.
        abundance_threshold: Minimum relative abundance to count as "present".

    Returns:
        Dictionary with plot_data, statistics, and core taxa lists.
    """
    # Normalize to relative abundance if counts detected
    if df.sum(axis=0).median() > 10:
        rel_abund = df.div(df.sum(axis=0), axis=1).fillna(0)
    else:
        rel_abund = df.copy()

    overall_core, overall_prev = _compute_core(rel_abund, prevalence_threshold, abundance_threshold)

    # Per-group cores if metadata provided
    group_cores = {}
    group_prevalence = {}
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        groups = metadata_df[group_column].dropna().unique()
        for group in groups:
            group_samples = metadata_df[metadata_df[group_column] == group].index.intersection(rel_abund.columns)
            if len(group_samples) == 0:
                continue
            group_df = rel_abund[list(group_samples)]
            core, prev = _compute_core(group_df, prevalence_threshold, abundance_threshold)
            group_cores[str(group)] = core
            group_prevalence[str(group)] = prev

    # Build statistics
    stats = {
        'n_taxa_total': len(df.index),
        'n_samples_total': len(df.columns),
        'prevalence_threshold': prevalence_threshold,
        'abundance_threshold': abundance_threshold,
        'n_core_taxa': len(overall_core),
        'core_fraction': len(overall_core) / len(df.index) if len(df.index) > 0 else 0.0,
        'mean_core_prevalence': float(np.mean(list(overall_prev.values()))) if overall_prev else 0.0,
    }

    if group_cores:
        for group, core in group_cores.items():
            stats[f'n_core_{group}'] = len(core)

    # Plotly figure: prevalence scatter + optional Venn-style bar
    plot_data = _plot_core_microbiome(
        rel_abund, overall_prev, overall_core,
        group_prevalence, group_cores,
        prevalence_threshold, abundance_threshold,
    )

    # Table data
    table_data = [
        {
            'taxon': taxon,
            'prevalence': overall_prev.get(taxon, 0.0),
            'is_core': taxon in overall_core,
            'mean_abundance': float(rel_abund.loc[taxon].mean()),
        }
        for taxon in rel_abund.index
    ]
    table_data = sorted(table_data, key=lambda x: x['prevalence'], reverse=True)

    return {
        'plot_data': plot_data,
        'statistics': stats,
        'core_taxa': overall_core,
        'prevalence': overall_prev,
        'group_cores': group_cores,
        'data': table_data,
    }


def _compute_core(
    rel_abund: pd.DataFrame,
    prevalence_threshold: float,
    abundance_threshold: float,
) -> tuple[List[str], Dict[str, float]]:
    """Compute core taxa and prevalence for a given abundance matrix."""
    prevalence = {}
    n_samples = len(rel_abund.columns)
    for taxon in rel_abund.index:
        present = (rel_abund.loc[taxon] > abundance_threshold).sum()
        prevalence[taxon] = float(present / n_samples)

    core_taxa = [t for t, p in prevalence.items() if p >= prevalence_threshold]
    return core_taxa, prevalence


def _plot_core_microbiome(
    rel_abund: pd.DataFrame,
    overall_prev: Dict[str, float],
    overall_core: List[str],
    group_prevalence: Dict[str, Dict[str, float]],
    group_cores: Dict[str, List[str]],
    prevalence_threshold: float,
    abundance_threshold: float,
) -> dict:
    """Generate Plotly figure for core microbiome visualization."""
    n_groups = len(group_cores)

    if n_groups > 1:
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('Prevalence vs Mean Abundance', 'Core Taxa by Group'),
            specs=[[{'type': 'scatter'}, {'type': 'bar'}]],
        )
    else:
        fig = go.Figure()

    # Plot 1: Prevalence vs Mean Abundance scatter
    mean_abund = rel_abund.mean(axis=1)
    x_vals = []
    y_vals = []
    colors = []
    text = []
    for taxon in rel_abund.index:
        x_vals.append(mean_abund.loc[taxon])
        y_vals.append(overall_prev[taxon])
        is_core = taxon in overall_core
        colors.append('#2ca02c' if is_core else '#1f77b4')
        text.append(f'{taxon}<br>Prevalence: {overall_prev[taxon]:.2%}<br>Mean Abund: {mean_abund.loc[taxon]:.4f}')

    scatter = go.Scatter(
        x=x_vals,
        y=y_vals,
        mode='markers',
        marker=dict(color=colors, size=8, opacity=0.7),
        text=text,
        hovertemplate='%{text}<extra></extra>',
        name='Taxa',
    )

    if n_groups > 1:
        fig.add_trace(scatter, row=1, col=1)
    else:
        fig.add_trace(scatter)

    # Add threshold lines
    hline = go.scatter.Shape(
        type='line',
        x0=0, x1=max(x_vals) * 1.1 if x_vals else 1,
        y0=prevalence_threshold, y1=prevalence_threshold,
        line=dict(color='red', width=1, dash='dash'),
    )
    if n_groups > 1:
        fig.add_hline(y=prevalence_threshold, line_dash='dash', line_color='red', row=1, col=1)
        fig.add_vline(x=abundance_threshold, line_dash='dash', line_color='red', row=1, col=1)
    else:
        fig.add_hline(y=prevalence_threshold, line_dash='dash', line_color='red')
        fig.add_vline(x=abundance_threshold, line_dash='dash', line_color='red')

    # Plot 2: Group-wise core bar (if multiple groups)
    if n_groups > 1:
        groups = list(group_cores.keys())
        core_counts = [len(group_cores[g]) for g in groups]
        shared_core = set.intersection(*[set(c) for c in group_cores.values()]) if group_cores else set()

        fig.add_trace(go.Bar(
            x=groups,
            y=core_counts,
            name='Core Taxa Count',
            marker_color='#2ca02c',
            text=core_counts,
            textposition='outside',
        ), row=1, col=2)

        # Annotation for shared core
        if shared_core:
            fig.add_annotation(
                x=0.5, y=-0.15,
                xref='paper', yref='paper',
                text=f'Shared core taxa across all groups: {len(shared_core)}',
                showarrow=False,
                font=dict(size=12),
            )

        fig.update_layout(
            title_text='Core Microbiome Analysis',
            height=500,
        )
        fig.update_xaxes(title_text='Mean Relative Abundance', row=1, col=1)
        fig.update_yaxes(title_text='Prevalence (fraction of samples)', row=1, col=1)
        fig.update_xaxes(title_text='Group', row=1, col=2)
        fig.update_yaxes(title_text='Number of Core Taxa', row=1, col=2)
    else:
        fig.update_layout(
            title='Core Microbiome Analysis',
            xaxis_title='Mean Relative Abundance',
            yaxis_title='Prevalence (fraction of samples)',
            height=500,
        )

    return fig.to_dict()
