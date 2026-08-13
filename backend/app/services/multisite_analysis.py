"""
Multi-site Analysis Module
==========================
Analyzes microbiome data across multiple study sites, body sites, cohorts, or timepoints.

Functions:
- multisite_pcoa: PCoA with all sites overlaid, colored by site
- multisite_permanova: Test site effects and site × group interactions
- multisite_markers: Site-specific differential abundance markers
- multisite_temporal: Longitudinal trajectory analysis
- multisite_network_compare: Cross-site network comparison

Input Requirements:
- Feature table (samples × taxa)
- Metadata with at least one of: Site, BodySite, Cohort, Location, Timepoint
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform
from scipy import stats

from app.services.analysis_engine import AnalysisEngine
from app.services.network_analysis import run_network_analysis
from app.services.metabolomics_analysis import run_metabolomics_marker_discovery

logger = logging.getLogger(__name__)


# ─────────────────────────────── Helper Functions

def _detect_site_column(metadata_df: pd.DataFrame) -> Optional[str]:
    """Auto-detect the column representing site/location/cohort."""
    candidates = ['Site', 'site', 'BodySite', 'body_site', 'Location', 'location',
                  'Cohort', 'cohort', 'City', 'city', 'Region', 'region',
                  'Body_Site', 'BODY_SITE', 'SITE']
    for col in candidates:
        if col in metadata_df.columns:
            return col
    # Fallback: look for columns with <= 10 unique values that might be sites
    for col in metadata_df.columns:
        if metadata_df[col].nunique() <= 10 and metadata_df[col].nunique() >= 2:
            if col.lower() not in ('visit', 'subject', 'id', 'sampleid', 'group', 'treatment'):
                return col
    return None


def _detect_subject_column(metadata_df: pd.DataFrame) -> Optional[str]:
    """Auto-detect the subject ID column for paired analysis."""
    candidates = ['Subject', 'subject', 'Participant', 'participant',
                  'Patient', 'patient', 'Individual', 'individual',
                  'Mouse', 'mouse', 'SUBJECT', 'PATIENT']
    for col in candidates:
        if col in metadata_df.columns:
            return col
    return None


def _detect_time_column(metadata_df: pd.DataFrame) -> Optional[str]:
    """Auto-detect the timepoint column for temporal analysis."""
    candidates = ['Timepoint', 'timepoint', 'Visit', 'visit', 'Day', 'day',
                  'Week', 'week', 'Month', 'month', 'Time', 'time',
                  'TIMESTAMP', 'Date', 'date']
    for col in candidates:
        if col in metadata_df.columns:
            return col
    return None


# ─────────────────────────────── 1. Multi-site PCoA

def run_multisite_pcoa(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    site_column: Optional[str] = None,
    subject_column: Optional[str] = None,
    group_column: Optional[str] = None,
    distance_metric: str = 'braycurtis',
    ordination_method: str = 'pcoa',
    connect_subjects: bool = False,
) -> Dict[str, Any]:
    """
    Principal Coordinate Analysis across multiple sites.
    All samples plotted together, colored by site, shaped by group.
    Optionally connect paired subjects across sites.
    """
    from skbio.stats.distance import DistanceMatrix
    from skbio.stats.ordination import pcoa as skbio_pcoa
    from sklearn.manifold import MDS

    # Auto-detect site column
    if site_column is None:
        site_column = _detect_site_column(metadata_df)
    if site_column is None:
        raise ValueError("No site column found in metadata. Please specify site_column.")

    # Prepare data
    common_samples = df.index.intersection(metadata_df.index)
    if len(common_samples) == 0:
        raise ValueError("No matching samples between data and metadata.")

    df_aligned = df.loc[common_samples]
    meta_aligned = metadata_df.loc[common_samples]
    sites = meta_aligned[site_column].unique()

    # Calculate distance matrix
    rel_abund = df_aligned.div(df_aligned.sum(axis=1), axis=0)
    dm = squareform(pdist(rel_abund.values, metric=distance_metric))

    # Ordination
    if ordination_method == 'pcoa':
        dm_skbio = DistanceMatrix(dm, ids=common_samples.tolist())
        pcoa_result = skbio_pcoa(dm_skbio)
        coords = pcoa_result.samples.iloc[:, :3]
        coords.columns = ['PC1', 'PC2', 'PC3']
        coords.index = common_samples
        ev = (pcoa_result.proportion_explained[:3] * 100).values
    else:  # nmds
        mds = MDS(n_components=2, metric=False, dissimilarity='precomputed', random_state=42)
        embeddings = mds.fit_transform(dm)
        coords = pd.DataFrame(embeddings[:, :2], index=common_samples, columns=['PC1', 'PC2'])
        ev = np.array([50.0, 30.0])  # placeholder

    # Build Plotly figure
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # Color palette for sites
    site_colors = _get_site_colors(sites)

    fig = go.Figure()

    # Plot each site
    for site in sorted(sites):
        mask = meta_aligned[site_column] == site
        samps = coords.index[mask]
        hover_text = [f"Sample: {s}<br>Site: {site}" for s in samps]
        if group_column and group_column in meta_aligned.columns:
            hover_text = [f"{t}<br>{group_column}: {meta_aligned.loc[s, group_column]}" for s, t in zip(samps, hover_text)]

        fig.add_trace(go.Scatter(
            x=coords.loc[samps, 'PC1'],
            y=coords.loc[samps, 'PC2'],
            mode='markers',
            name=str(site),
            marker=dict(size=10, color=site_colors.get(site, '#999999'), opacity=0.8,
                       line=dict(width=0.5, color='white')),
            text=hover_text,
            hovertemplate='%{text}<extra></extra>',
        ))

    # Connect paired subjects across sites
    if connect_subjects and subject_column and subject_column in meta_aligned.columns:
        subjects = meta_aligned[subject_column].unique()
        for subj in subjects:
            subj_mask = meta_aligned[subject_column] == subj
            subj_samps = coords.index[subj_mask]
            if len(subj_samps) > 1:
                fig.add_trace(go.Scatter(
                    x=coords.loc[subj_samps, 'PC1'],
                    y=coords.loc[subj_samps, 'PC2'],
                    mode='lines',
                    line=dict(color='grey', width=0.5, dash='dot'),
                    showlegend=False,
                    hoverinfo='skip',
                ))

    fig.update_layout(
        title=f'Multi-site {ordination_method.upper()} ({distance_metric})',
        xaxis_title=f'{coords.columns[0]} ({ev[0]:.1f}%)',
        yaxis_title=f'{coords.columns[1]} ({ev[1]:.1f}%)',
        template='plotly_white',
        legend_title_text='Site',
        width=800, height=600,
    )

    # Per-site centroids
    centroids = {}
    for site in sites:
        mask = meta_aligned[site_column] == site
        centroids[str(site)] = {
            'pc1': float(coords.loc[mask, 'PC1'].mean()),
            'pc2': float(coords.loc[mask, 'PC2'].mean()),
            'n_samples': int(mask.sum()),
        }

    return {
        'plot_data': fig.to_dict(),
        'coordinates': coords.to_dict(),
        'eigenvalues': ev.tolist(),
        'n_sites': len(sites),
        'sites': [str(s) for s in sites],
        'site_column': site_column,
        'subject_column': subject_column,
        'centroids': centroids,
        'n_samples': len(common_samples),
    }


# ─────────────────────────────── 2. Multi-site PERMANOVA

def run_multisite_permanova(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    site_column: Optional[str] = None,
    group_column: Optional[str] = None,
    distance_metric: str = 'braycurtis',
    permutations: int = 999,
) -> Dict[str, Any]:
    """
    PERMANOVA testing site effects, group effects, and site × group interaction.
    """
    from skbio.stats.distance import DistanceMatrix
    from skbio.stats.distance import permanova as skbio_permanova

    if site_column is None:
        site_column = _detect_site_column(metadata_df)
    if site_column is None:
        raise ValueError("No site column found.")

    common = df.index.intersection(metadata_df.index)
    df_aligned = df.loc[common]
    meta = metadata_df.loc[common]

    rel_abund = df_aligned.div(df_aligned.sum(axis=1), axis=0)
    dm = squareform(pdist(rel_abund.values, metric=distance_metric))
    dm_obj = DistanceMatrix(dm, ids=common.tolist())

    results = {}

    # Test 1: Site effect
    try:
        result_site = skbio_permanova(dm_obj, meta, column=site_column, permutations=permutations)
        results['site'] = {
            'F': float(result_site['test statistic']),
            'p': float(result_site['p-value']),
            'n_groups': meta[site_column].nunique(),
            'significant': float(result_site['p-value']) < 0.05,
        }
    except Exception as e:
        results['site'] = {'error': str(e)}

    # Test 2: Group effect (if provided)
    if group_column and group_column in meta.columns:
        try:
            result_group = skbio_permanova(dm_obj, meta, column=group_column, permutations=permutations)
            results['group'] = {
                'F': float(result_group['test statistic']),
                'p': float(result_group['p-value']),
                'n_groups': meta[group_column].nunique(),
                'significant': float(result_group['p-value']) < 0.05,
            }
        except Exception as e:
            results['group'] = {'error': str(e)}

    # Test 3: Pairwise between sites
    pairwise = []
    sites = meta[site_column].unique()
    for i, s1 in enumerate(sites):
        for s2 in sites[i+1:]:
            mask = meta[site_column].isin([s1, s2])
            if mask.sum() < 4:
                continue
            sub_dm = DistanceMatrix(dm[mask.values][:, mask.values], ids=common[mask].tolist())
            sub_meta = meta.loc[mask]
            try:
                r = skbio_permanova(sub_dm, sub_meta, column=site_column, permutations=min(99, permutations))
                pairwise.append({
                    'comparison': f'{s1} vs {s2}',
                    'F': float(r['test statistic']),
                    'p': float(r['p-value']),
                    'significant': float(r['p-value']) < 0.05,
                })
            except Exception:
                pass

    results['pairwise'] = pairwise

    return {
        'statistics': results,
        'site_column': site_column,
        'group_column': group_column,
        'n_samples': len(common),
        'n_sites': len(sites),
        'permutations': permutations,
    }


# ─────────────────────────────── 3. Multi-site Markers

def run_multisite_markers(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    site_column: Optional[str] = None,
    reference_site: Optional[str] = None,
    subject_column: Optional[str] = None,
    pvalue_threshold: float = 0.05,
    fc_threshold: float = 1.5,
) -> Dict[str, Any]:
    """
    Differential abundance markers for each site vs reference site.
    Uses CLR + Wilcoxon rank-sum (or paired Wilcoxon if subjects match).
    """
    if site_column is None:
        site_column = _detect_site_column(metadata_df)
    if site_column is None:
        raise ValueError("No site column found.")

    common = df.index.intersection(metadata_df.index)
    df_aligned = df.loc[common]
    meta = metadata_df.loc[common]
    sites = meta[site_column].unique()

    if reference_site is None:
        reference_site = sites[0]

    # CLR transformation
    def _clr(df_counts):
        df_pseudo = df_counts.replace(0, 1e-6)
        log_df = np.log(df_pseudo)
        return log_df.subtract(log_df.mean(axis=1), axis=0)

    clr_df = _clr(df_aligned)

    site_results = {}
    all_sig_features = set()

    for site in sites:
        if str(site) == str(reference_site):
            continue

        site_mask = meta[site_column] == site
        ref_mask = meta[site_column] == reference_site

        if site_mask.sum() < 2 or ref_mask.sum() < 2:
            continue

        # Paired analysis if subjects match
        paired = False
        if subject_column and subject_column in meta.columns:
            site_subjects = set(meta.loc[site_mask, subject_column].dropna())
            ref_subjects = set(meta.loc[ref_mask, subject_column].dropna())
            if len(site_subjects & ref_subjects) >= 3:
                paired = True

        site_features = []
        for col in clr_df.columns:
            site_vals = clr_df.loc[site_mask, col].values
            ref_vals = clr_df.loc[ref_mask, col].values

            if paired:
                try:
                    _, p = stats.wilcoxon(site_vals, ref_vals)
                except Exception:
                    _, p = stats.mannwhitneyu(site_vals, ref_vals, alternative='two-sided')
            else:
                _, p = stats.mannwhitneyu(site_vals, ref_vals, alternative='two-sided')

            # FC on relative abundance
            rel = df_aligned.div(df_aligned.sum(axis=1), axis=0)
            mean_site = rel.loc[site_mask, col].mean()
            mean_ref = rel.loc[ref_mask, col].mean()
            fc = mean_site / (mean_ref + 1e-9) if mean_ref > 0 else 1.0
            log2fc = np.log2(max(fc, 1e-10))

            site_features.append({
                'feature': col,
                'pvalue': float(p),
                'log2_fc': float(log2fc),
                'mean_site': float(mean_site),
                'mean_ref': float(mean_ref),
                'direction': 'up' if log2fc > 0 else 'down',
            })

        # BH FDR
        from statsmodels.stats.multitest import multipletests
        pvals = [f['pvalue'] for f in site_features]
        try:
            _, padj, _, _ = multipletests(pvals, method='fdr_bh')
        except Exception:
            padj = pvals

        for i, f in enumerate(site_features):
            f['padj'] = float(padj[i])
            f['significant'] = (f['padj'] < pvalue_threshold) and (abs(f['log2_fc']) > np.log2(fc_threshold))

        sig = [f for f in site_features if f['significant']]
        all_sig_features.update(f['feature'] for f in sig)

        site_results[str(site)] = {
            'n_significant': len(sig),
            'n_up': len([f for f in sig if f['direction'] == 'up']),
            'n_down': len([f for f in sig if f['direction'] == 'down']),
            'all_features': site_features,
            'significant_features': sig,
        }

    return {
        'site_results': site_results,
        'reference_site': str(reference_site),
        'n_total_significant': len(all_sig_features),
        'site_column': site_column,
        'paired_analysis': paired if 'paired' in dir() else False,
    }


# ─────────────────────────────── 4. Multi-site Temporal

def run_multisite_temporal(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    time_column: Optional[str] = None,
    subject_column: Optional[str] = None,
    group_column: Optional[str] = None,
    site_column: Optional[str] = None,
    distance_metric: str = 'braycurtis',
) -> Dict[str, Any]:
    """
    Longitudinal trajectory analysis across timepoints.
    Includes trajectory PCoA, time trend test, and subject progression.
    """
    if time_column is None:
        time_column = _detect_time_column(metadata_df)
    if time_column is None:
        raise ValueError("No time column found.")

    common = df.index.intersection(metadata_df.index)
    df_aligned = df.loc[common]
    meta = metadata_df.loc[common]

    # Ensure time is numeric
    time_vals = meta[time_column]
    try:
        time_numeric = pd.to_numeric(time_vals)
    except Exception:
        time_numeric = pd.Categorical(time_vals).codes

    # PCoA trajectory
    from skbio.stats.distance import DistanceMatrix
    from skbio.stats.ordination import pcoa as skbio_pcoa

    rel_abund = df_aligned.div(df_aligned.sum(axis=1), axis=0)
    dm = squareform(pdist(rel_abund.values, metric=distance_metric))
    dm_obj = DistanceMatrix(dm, ids=common.tolist())
    pcoa_result = skbio_pcoa(dm_obj)
    coords = pcoa_result.samples.iloc[:, :2]
    coords.columns = ['PC1', 'PC2']
    coords.index = common

    # Build trajectory plot
    import plotly.graph_objects as go

    fig = go.Figure()
    colors = _get_time_colors(time_numeric)

    # Scatter with time color
    fig.add_trace(go.Scatter(
        x=coords['PC1'],
        y=coords['PC2'],
        mode='markers',
        marker=dict(
            size=10,
            color=time_numeric.values,
            colorscale='Viridis',
            showscale=True,
            colorbar=dict(title=str(time_column)),
        ),
        text=[f"Sample: {s}<br>Time: {t}" for s, t in zip(common, time_vals)],
        hovertemplate='%{text}<extra></extra>',
    ))

    # Connect subjects across time
    if subject_column and subject_column in meta.columns:
        for subj in meta[subject_column].unique():
            subj_mask = meta[subject_column] == subj
            if subj_mask.sum() > 1:
                subj_coords = coords.loc[subj_mask].sort_values(by='PC1')
                fig.add_trace(go.Scatter(
                    x=subj_coords['PC1'],
                    y=subj_coords['PC2'],
                    mode='lines',
                    line=dict(color='rgba(100,100,100,0.3)', width=1),
                    showlegend=False,
                    hoverinfo='skip',
                ))

    fig.update_layout(
        title=f'Temporal Trajectory ({distance_metric})',
        xaxis_title=f'PC1 ({pcoa_result.proportion_explained[0]*100:.1f}%)',
        yaxis_title=f'PC2 ({pcoa_result.proportion_explained[1]*100:.1f}%)',
        template='plotly_white',
        width=800, height=600,
    )

    # Time trend: correlation between PC1 and time
    from scipy.stats import spearmanr
    corr_pc1, p_pc1 = spearmanr(coords['PC1'].values, time_numeric.values)
    corr_pc2, p_pc2 = spearmanr(coords['PC2'].values, time_numeric.values)

    # PERMANOVA by time (if discrete)
    time_groups = meta[time_column].nunique()
    permanova_time = None
    if time_groups >= 2 and time_groups <= len(common) * 0.8:
        try:
            r = skbio_permanova(dm_obj, meta, column=time_column, permutations=999)
            permanova_time = {
                'F': float(r['test statistic']),
                'p': float(r['p-value']),
            }
        except Exception:
            pass

    return {
        'plot_data': fig.to_dict(),
        'time_column': time_column,
        'n_timepoints': int(time_groups),
        'time_trend': {
            'pc1_time_correlation': {'rho': float(corr_pc1), 'p': float(p_pc1)},
            'pc2_time_correlation': {'rho': float(corr_pc2), 'p': float(p_pc2)},
        },
        'permanova_time': permanova_time,
        'n_samples': len(common),
    }


# ─────────────────────────────── 5. Multi-site Network Comparison

def run_multisite_network_compare(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    site_column: Optional[str] = None,
    threshold: float = 0.3,
) -> Dict[str, Any]:
    """
    Compare correlation networks across sites.
    Identifies shared edges, unique edges, and hub taxa per site.
    """
    if site_column is None:
        site_column = _detect_site_column(metadata_df)
    if site_column is None:
        raise ValueError("No site column found.")

    common = df.index.intersection(metadata_df.index)
    df_aligned = df.loc[common]
    meta = metadata_df.loc[common]
    sites = meta[site_column].unique()

    # Build network per site
    networks = {}
    for site in sites:
        mask = meta[site_column] == site
        site_df = df_aligned.loc[mask]
        try:
            net_result = run_network_analysis(site_df, threshold=threshold)
            networks[str(site)] = net_result
        except Exception as e:
            logger.warning(f"Failed to build network for site {site}: {e}")
            networks[str(site)] = None

    # Compare edges
    all_edges = {}
    shared_edges = set()
    unique_edges = {}

    for site, net in networks.items():
        if net is None:
            continue
        edges = set()
        for edge in net.get('edges', []):
            e = tuple(sorted([edge['source'], edge['target']]))
            edges.add(e)
        all_edges[site] = edges
        if not shared_edges:
            shared_edges = set(edges)
        else:
            shared_edges &= edges

    for site, edges in all_edges.items():
        unique_edges[site] = list(edges - shared_edges)

    # Hub taxa (top degree nodes per site)
    hub_taxa = {}
    for site, net in networks.items():
        if net is None:
            continue
        degrees = {}
        for edge in net.get('edges', []):
            for node in [edge['source'], edge['target']]:
                degrees[node] = degrees.get(node, 0) + 1
        sorted_degrees = sorted(degrees.items(), key=lambda x: x[1], reverse=True)
        hub_taxa[site] = [{'taxon': t, 'degree': d} for t, d in sorted_degrees[:10]]

    return {
        'networks': networks,
        'shared_edges': list(shared_edges),
        'n_shared_edges': len(shared_edges),
        'unique_edges': unique_edges,
        'hub_taxa': hub_taxa,
        'site_column': site_column,
        'n_sites': len(sites),
    }


# ─────────────────────────────── Utility Functions

def _get_site_colors(sites) -> Dict[str, str]:
    """Generate distinct colors for sites."""
    palette = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
    ]
    return {str(site): palette[i % len(palette)] for i, site in enumerate(sorted(sites))}


def _get_time_colors(time_series) -> List[str]:
    """Generate colors for time points."""
    n = len(time_series)
    return [f'rgba({int(50 + 200 * i / max(n-1, 1))}, {int(100 + 150 * (1 - i / max(n-1, 1)))}, 150, 0.7)' for i in range(n)]
