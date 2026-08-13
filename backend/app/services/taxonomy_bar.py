"""
Taxonomy Bar Plot
=================
Stacked bar chart showing community composition at specified taxonomic level.
Standard Figure 1 in microbiome studies.

Reference: phyloseq plot_bar(), qiime taxa barplot
"""
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _parse_taxonomy_level(taxa_names: List[str], level: str = 'genus') -> pd.Series:
    """Extract taxonomic level from full taxonomy strings (MetaPhlAn format)."""
    level_map = {
        'kingdom': 'k__', 'phylum': 'p__', 'class': 'c__', 'order': 'o__',
        'family': 'f__', 'genus': 'g__', 'species': 's__',
    }
    prefix = level_map.get(level.lower(), 'g__')
    
    parsed = []
    for name in taxa_names:
        if '|' in name:
            # MetaPhlAn format: k__Bacteria|p__Firmicutes|g__Lactobacillus
            parts = name.split('|')
            for part in reversed(parts):
                if part.startswith(prefix):
                    parsed.append(part.split('__')[1] if '__' in part else part)
                    break
            else:
                parsed.append(name)
        else:
            # Simple genus name
            parsed.append(name)
    
    return pd.Series(parsed, index=taxa_names)


def run_taxonomy_bar(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    group_column: Optional[str] = None,
    tax_level: str = 'genus',
    top_n: int = 15,
    sort_by: str = 'abundance',
) -> Dict[str, Any]:
    """
    Generate stacked bar plot of community composition.

    Args:
        df: Abundance/count matrix (features x samples or samples x taxa)
        metadata_df: Sample metadata
        group_column: Column for grouping samples
        tax_level: Taxonomic level to aggregate ('phylum', 'genus', 'species')
        top_n: Number of top taxa to show (rest grouped as 'Others')
        sort_by: Sort samples by 'abundance' or 'group'

    Returns:
        Dict with plot_data, statistics
    """
    # Auto-detect orientation: if rows look like taxa names, transpose
    first_idx = str(df.index[0])
    if '|' in first_idx or '__' in first_idx:
        df = df.T

    # Normalize to relative abundance (rows = samples)
    rel_abund = df.div(df.sum(axis=1), axis=0) * 100

    # Parse taxonomy level and aggregate
    taxa_parsed = _parse_taxonomy_level(rel_abund.columns.tolist(), tax_level)
    grouping = pd.Series({col: taxa_parsed.get(col, col) for col in rel_abund.columns})
    aggregated = rel_abund.groupby(grouping, axis=1).sum()

    # Identify top N taxa
    mean_abundance = aggregated.mean(axis=0).sort_values(ascending=False)
    top_taxa = mean_abundance.head(top_n).index.tolist()
    
    # Group others
    others = aggregated.columns.difference(top_taxa)
    if len(others) > 0:
        aggregated['Others'] = aggregated[others].sum(axis=1)
        plot_df = aggregated[top_taxa + ['Others']]
    else:
        plot_df = aggregated[top_taxa]

    # Sort samples
    sample_order = plot_df.index.tolist()
    if group_column and metadata_df is not None and group_column in metadata_df.columns:
        meta_aligned = metadata_df.loc[plot_df.index]
        # Sort by group then by total abundance
        plot_df['_group'] = meta_aligned[group_column]
        plot_df['_total'] = plot_df.drop('_group', axis=1).sum(axis=1)
        plot_df = plot_df.sort_values(['_group', '_total'], ascending=[True, False])
        sample_order = plot_df.index.tolist()
        plot_df = plot_df.drop(['_group', '_total'], axis=1)
    else:
        plot_df = plot_df.loc[plot_df.sum(axis=1).sort_values(ascending=False).index]
        sample_order = plot_df.index.tolist()

    # Build Plotly figure
    import plotly.graph_objects as go

    # Color palette
    palette = [
        '#1e40af', '#d97706', '#0f766e', '#dc2626', '#7c3aed',
        '#0891b2', '#be185d', '#4d7c0f', '#b45309', '#4338ca',
        '#0e7490', '#a16207', '#047857', '#c2410c', '#6d28d9',
        '#9ca3af',
    ]

    fig = go.Figure()

    for i, taxon in enumerate(plot_df.columns):
        color = palette[i % len(palette)]
        fig.add_trace(go.Bar(
            name=taxon,
            x=sample_order,
            y=plot_df.loc[sample_order, taxon].values,
            marker_color=color,
            hovertemplate=f'<b>{taxon}</b><br>Sample: %{{x}}<br>Abundance: %{{y:.2f}}%<extra></extra>',
        ))

    fig.update_layout(
        barmode='stack',
        title=f'Community Composition ({tax_level.title()} Level)',
        xaxis_title='Sample',
        yaxis_title='Relative Abundance (%)',
        template='plotly_white',
        width=max(800, len(sample_order) * 20),
        height=500,
        legend_title_text=tax_level.title(),
        xaxis=dict(tickangle=45),
    )

    # Group averages if metadata provided
    group_means = {}
    if group_column and metadata_df is not None and group_column in metadata_df.columns:
        for group in metadata_df[group_column].unique():
            group_samples = metadata_df[metadata_df[group_column] == group].index
            group_samples = [s for s in group_samples if s in plot_df.index]
            if group_samples:
                group_means[str(group)] = plot_df.loc[group_samples].mean().to_dict()

    return {
        'plot_data': fig.to_dict(),
        'statistics': {
            'tax_level': tax_level,
            'n_taxa_shown': len(plot_df.columns),
            'n_samples': len(sample_order),
            'top_taxa': top_taxa,
            'group_averages': group_means,
            'mean_dominant_taxon': float(mean_abundance.iloc[0]) if len(mean_abundance) > 0 else 0,
        },
    }


def run_core_microbiome(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    group_column: Optional[str] = None,
    prevalence_threshold: float = 0.5,
    abundance_threshold: float = 0.01,
) -> Dict[str, Any]:
    """
    Identify core microbiome (taxa present in most samples).

    Args:
        df: Abundance matrix (features x samples or samples x taxa)
        metadata_df: Sample metadata
        group_column: Column for group-specific core
        prevalence_threshold: Minimum fraction of samples taxon must be present in
        abundance_threshold: Minimum relative abundance to count as "present"

    Returns:
        Dict with plot_data, core_taxa list
    """
    # Auto-detect orientation: if rows look like taxa names, transpose
    first_idx = str(df.index[0])
    if '|' in first_idx or '__' in first_idx:
        df = df.T

    rel_abund = df.div(df.sum(axis=1), axis=0)

    # Overall core
    prevalence = (rel_abund >= abundance_threshold).mean(axis=0)
    core_taxa = prevalence[prevalence >= prevalence_threshold].index.tolist()
    core_prevalence = prevalence[core_taxa].to_dict()

    # Group-specific core
    group_core = {}
    if group_column and metadata_df is not None and group_column in metadata_df.columns:
        for group in metadata_df[group_column].unique():
            group_samples = metadata_df[metadata_df[group_column] == group].index
            group_samples = [s for s in group_samples if s in rel_abund.index]
            if group_samples:
                group_prev = (rel_abund.loc[group_samples] >= abundance_threshold).mean(axis=0)
                group_core[str(group)] = {
                    'core_taxa': group_prev[group_prev >= prevalence_threshold].index.tolist(),
                    'prevalence': group_prev[group_prev >= prevalence_threshold].to_dict(),
                }

    # Plot: prevalence vs abundance scatter
    import plotly.graph_objects as go

    mean_abundance = rel_abund.mean(axis=0)

    fig = go.Figure()

    # Non-core taxa
    non_core = [t for t in rel_abund.columns if t not in core_taxa]
    fig.add_trace(go.Scatter(
        x=[mean_abundance[t] for t in non_core],
        y=[prevalence[t] for t in non_core],
        mode='markers',
        name=f'Non-core (n={len(non_core)})',
        marker=dict(size=8, color='rgba(150,150,150,0.5)', line=dict(width=0.5, color='white')),
        text=non_core,
        hovertemplate='<b>%{text}</b><br>Mean abundance: %{x:.4f}<br>Prevalence: %{y:.2f}<extra></extra>',
    ))

    # Core taxa
    if core_taxa:
        fig.add_trace(go.Scatter(
            x=[mean_abundance[t] for t in core_taxa],
            y=[prevalence[t] for t in core_taxa],
            mode='markers',
            name=f'Core (n={len(core_taxa)})',
            marker=dict(size=12, color='#1e40af', line=dict(width=1, color='white')),
            text=core_taxa,
            hovertemplate='<b>%{text}</b><br>Mean abundance: %{x:.4f}<br>Prevalence: %{y:.2f}<extra></extra>',
        ))

    # Threshold lines
    fig.add_hline(y=prevalence_threshold, line_dash="dash", line_color="red",
                  annotation_text=f"Prevalence = {prevalence_threshold}")
    fig.add_vline(x=abundance_threshold, line_dash="dash", line_color="red",
                  annotation_text=f"Abundance = {abundance_threshold}")

    fig.update_layout(
        title=f'Core Microbiome Detection (prevalence ≥ {prevalence_threshold}, abundance ≥ {abundance_threshold})',
        xaxis_title='Mean Relative Abundance',
        yaxis_title='Prevalence (fraction of samples)',
        template='plotly_white',
        width=700,
        height=500,
    )

    return {
        'plot_data': fig.to_dict(),
        'statistics': {
            'n_core_taxa': len(core_taxa),
            'core_taxa': core_taxa,
            'core_prevalence': {t: float(p) for t, p in core_prevalence.items()},
            'group_core': group_core,
            'prevalence_threshold': prevalence_threshold,
            'abundance_threshold': abundance_threshold,
        },
    }
